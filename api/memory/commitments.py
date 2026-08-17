"""open loops. commitments mined from sent messages, both directions.

nightly (called from consolidation): scan the last two days of archived
messages for promises — yours ("i'll send the deck friday") and theirs
("he said he'd intro me tuesday") — and file them as commitments. the
digest surfaces open ones with their age; resolve from the digest, chat,
or the api. extraction prefers the free local model and falls back to
claude when a key exists.

only ro can verify a loop against ground truth (did the file actually go
out?) because the ground truth spans imessage + email + disk. v1 tracks
and surfaces; verification hooks come with usage.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from api.memory.db import db
from api.observability import budget
from api.observability.logging import log

EXTRACT_PROMPT = (
    "extract commitments from these messages. a commitment is a concrete "
    "promise to do something, either by 'me' (from_me lines) or by the "
    "other person. output ONLY a json array, each item: "
    '{"direction": "mine"|"theirs", "who": "<other party>", '
    '"what": "<the promise, short>", "due_hint": "<when, if stated>"} '
    "no commitments means []. no invention."
)


async def _recent_sent(hours: int = 48) -> list[dict[str, Any]]:
    rows = await db.fetch(
        """select contact_key, sender, from_me, body from archive_messages
           where archived_at > now() - make_interval(hours => $1)
             and not vault
           order by sent_at asc nulls last limit 300""",
        hours,
    )
    return [dict(r) for r in rows]


def _parse(raw: str) -> list[dict[str, Any]]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


async def extract() -> dict[str, Any]:
    """mine recent messages for commitments. local model first."""
    msgs = await _recent_sent()
    if len(msgs) < 2:
        return {"found": 0, "reason": "not enough recent messages"}

    transcript = "\n".join(
        f"[{m['contact_key']}] {'me' if m['from_me'] else (m['sender'] or 'them')}: {m['body'][:300]}"
        for m in msgs
    )[:50_000]

    budget.set_run("open-loops")
    items: list[dict[str, Any]] = []
    try:
        from api.observability import llm_local
        local = await llm_local.chat(system=EXTRACT_PROMPT, user=transcript, max_tokens=800)
        if local:
            items = _parse(local)
    except Exception:
        items = []

    if not items:
        from api.observability import claude as claude_mod
        if claude_mod.configured():
            allowed, _ = await budget.allow_run("open-loops")
            if allowed:
                from api.config import settings
                from api.observability.claude import claude_client
                resp = await claude_client.message(
                    model=settings.model_cheap,
                    system=EXTRACT_PROMPT,
                    messages=[{"role": "user", "content": transcript}],
                    max_tokens=800,
                    temperature=0.0,
                )
                items = _parse("".join(b.text for b in resp.content if b.type == "text"))

    saved = 0
    for it in items[:20]:
        what = str(it.get("what") or "").strip()
        if len(what) < 5:
            continue
        dup = await db.fetchrow(
            """select 1 from commitments
               where status = 'open' and lower(what) = lower($1)""",
            what[:400],
        )
        if dup:
            continue
        await db.execute(
            """insert into commitments (direction, who, what, due_hint, source)
               values ($1, $2, $3, $4, 'archive')""",
            "mine" if it.get("direction") == "mine" else "theirs",
            str(it.get("who") or "")[:200], what[:400],
            str(it.get("due_hint") or "")[:120],
        )
        saved += 1
    return {"found": len(items), "saved": saved}


async def open_loops(limit: int = 12) -> list[dict[str, Any]]:
    rows = await db.fetch(
        """select id::text, direction, who, what, due_hint,
                  extract(day from now() - created_at)::int as age_days
           from commitments where status = 'open'
           order by created_at asc limit $1""",
        limit,
    )
    return [dict(r) for r in rows]


async def resolve(commitment_id: str, status: str = "done") -> bool:
    if status not in ("done", "dropped"):
        raise ValueError("status must be done or dropped")
    row = await db.fetchrow(
        """update commitments set status = $2, resolved_at = now()
           where id = $1 and status = 'open' returning id""",
        uuid.UUID(commitment_id), status,
    )
    return row is not None
