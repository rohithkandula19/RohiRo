"""entity graph — extract people/projects/places from raw_events.

every 30min the loop:
  1. picks unprocessed raw_events since the last watermark
  2. asks claude (cheap model) for a structured list of entities mentioned
  3. upserts each entity into `entities` (seen_count++, last_seen_at=now())
  4. writes one row per (entity, event) into `entity_mentions`

readers:
- find_entity(name)          fuzzy lookup by name
- entity_recent_events(id)   last N events that mentioned it
- entity_profile(name)       small dict for prompt injection
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from api.config import settings
from api.memory.db import db
from api.observability.claude import claude_client
from api.observability.logging import log

EXTRACT_PROMPT = """from this list of events, extract the entities that were mentioned.

return a JSON object with one key: "entities" — a list of small objects, each:
  - "kind":   "person" | "project" | "place" | "company" | "paper" | "repo"
  - "name":   the canonical name. for people: "Sarah Lin" not "sarah". no
              handles or emails — keep names human-readable.
  - "events": list of EVENT_IDs from the input that mention this entity
              (only ones you're confident about)

skip generic nouns ("meeting", "email", "the call"). skip ro itself.
output strictly JSON, no fences.

example output:
{"entities":[
  {"kind":"person","name":"Sarah Lin","events":["abc-123","def-456"]},
  {"kind":"company","name":"Photon Labs","events":["abc-123"]},
  {"kind":"repo","name":"rohflow","events":["xyz-789"]}
]}
"""


@dataclass
class Entity:
    id: str
    kind: str
    name: str
    summary: str
    seen_count: int
    last_seen_at: str


# ----- extractor -----


async def run_extraction(*, since_id: Optional[str] = None, limit: int = 60) -> dict[str, Any]:
    """pull recent events; ask claude for entities; upsert."""
    rows = await _fetch_events(since_id=since_id, limit=limit)
    if not rows:
        return {"events_scanned": 0}

    lines = [f"{r['id']}: [{r['source']}/{r['kind']}] {r['summary']}" for r in rows]
    user_msg = "events:\n" + "\n".join(lines)
    try:
        resp = await claude_client.message(
            model=settings.model_cheap,
            system=EXTRACT_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=1500,
            temperature=0.1,
        )
        raw = "".join(b.text for b in resp.content if b.type == "text").strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
    except Exception as e:
        log.warning("entity extractor parse failed", error=str(e))
        return {"events_scanned": len(rows), "error": str(e)}

    ents = data.get("entities") or []
    by_id = {r["id"]: r for r in rows}
    created = 0
    updated = 0
    mentions = 0
    for e in ents:
        kind = (e.get("kind") or "").strip().lower()
        name = (e.get("name") or "").strip()
        if not (kind and name):
            continue
        if kind not in {"person", "project", "place", "company", "paper", "repo"}:
            continue
        ent_id, is_new = await _upsert_entity(kind=kind, name=name)
        if is_new:
            created += 1
        else:
            updated += 1
        for eid in e.get("events", []) or []:
            if eid not in by_id:
                continue
            try:
                await db.execute(
                    """insert into entity_mentions (entity_id, event_id) values ($1, $2)
                       on conflict do nothing""",
                    uuid.UUID(ent_id), uuid.UUID(eid),
                )
                mentions += 1
            except Exception:
                continue

    last_id = rows[-1]["id"]
    await _set_watermark(last_id)
    return {"events_scanned": len(rows), "entities_created": created,
            "entities_updated": updated, "mentions_written": mentions,
            "watermark": last_id}


async def _fetch_events(*, since_id: Optional[str], limit: int) -> list[dict[str, Any]]:
    """ordered by happened_at asc so we always advance. uses created_at not id."""
    if since_id is None:
        since_id = await _get_watermark()
    if since_id:
        rows = await db.fetch(
            """with cutoff as (select happened_at from raw_events where id = $1)
               select id::text, happened_at, source, kind, summary
               from raw_events, cutoff
               where raw_events.happened_at > cutoff.happened_at
               order by happened_at asc limit $2""",
            uuid.UUID(since_id), limit,
        )
    else:
        rows = await db.fetch(
            """select id::text, happened_at, source, kind, summary
               from raw_events order by happened_at asc limit $1""",
            limit,
        )
    return [dict(r) for r in rows]


async def _upsert_entity(*, kind: str, name: str) -> tuple[str, bool]:
    """returns (id, is_new)."""
    row = await db.fetchrow(
        """insert into entities (kind, name) values ($1, $2)
           on conflict (kind, name) do update
             set seen_count = entities.seen_count + 1,
                 last_seen_at = now()
           returning id::text, (xmax = 0) as is_new""",
        kind, name,
    )
    return row["id"], bool(row["is_new"])


async def _get_watermark() -> Optional[str]:
    row = await db.fetchrow(
        """select external_id from seen_keys
           where source = 'entity_extractor' and external_id like 'event_id:%'
           order by first_seen_at desc limit 1"""
    )
    if not row:
        return None
    try:
        return row["external_id"].split(":", 1)[1]
    except Exception:
        return None


async def _set_watermark(event_id: str) -> None:
    await db.execute(
        """insert into seen_keys (source, external_id) values ('entity_extractor', $1)
           on conflict do nothing""",
        f"event_id:{event_id}",
    )


# ----- read paths -----


async def find_entity(name_query: str, limit: int = 5) -> list[Entity]:
    rows = await db.fetch(
        """select id::text, kind, name, coalesce(summary, '') as summary,
                  seen_count, last_seen_at,
                  similarity(name, $1) as score
           from entities
           where name ilike '%' || $1 || '%' or name % $1
           order by score desc, seen_count desc
           limit $2""",
        name_query, limit,
    )
    return [_to_entity(r) for r in rows]


async def entity_recent_events(entity_id: str, limit: int = 8) -> list[dict[str, Any]]:
    rows = await db.fetch(
        """select e.id::text, e.happened_at, e.source, e.kind, e.summary
           from raw_events e
           join entity_mentions m on m.event_id = e.id
           where m.entity_id = $1
           order by e.happened_at desc
           limit $2""",
        uuid.UUID(entity_id), limit,
    )
    return [
        {**dict(r), "happened_at": r["happened_at"].isoformat() if r["happened_at"] else ""}
        for r in rows
    ]


async def entity_profile(name_query: str) -> Optional[dict[str, Any]]:
    """return the top-matching entity + recent events. for prompt injection."""
    hits = await find_entity(name_query, limit=1)
    if not hits:
        return None
    ent = hits[0]
    events = await entity_recent_events(ent.id, limit=8)
    return {
        "id": ent.id, "kind": ent.kind, "name": ent.name,
        "seen_count": ent.seen_count, "last_seen_at": ent.last_seen_at,
        "summary": ent.summary,
        "recent_events": events,
    }


def _to_entity(r: Any) -> Entity:
    return Entity(
        id=r["id"], kind=r["kind"], name=r["name"],
        summary=r.get("summary", "") or "",
        seen_count=r["seen_count"],
        last_seen_at=r["last_seen_at"].isoformat() if r["last_seen_at"] else "",
    )
