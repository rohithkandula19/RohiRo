"""nightly memory consolidation.

three passes, all idempotent, run by launchd (ro.consolidate.plist):

1. entity refresh: bump seen counts for entities named in the last day.
2. summarization: sessions whose turns are older than 14 days get one
   claude-written summary row (role='summary', embedded for retrieval),
   then their raw turns are deleted. ro remembers what mattered, not
   every keystroke. capped per night so a backlog cannot blow the budget.
3. cleanup: very old, low-signal rows go away.

runs attribute their spend to 'consolidate' via the budget contextvar and
respect the daily cap by checking allow_run first.
"""

from __future__ import annotations

import asyncio
import json

from api.config import settings
from api.memory.db import db
from api.observability import budget
from api.observability.claude import claude_client
from api.observability.logging import log, setup_logging

SUMMARIZE_AFTER_DAYS = 14
MAX_SESSIONS_PER_NIGHT = 10
MAX_TURNS_PER_SESSION = 200

SUMMARY_PROMPT = (
    "summarize this conversation for long term memory. keep: decisions, facts "
    "about people and projects, preferences expressed, commitments made, "
    "anything ro should remember months from now. drop: pleasantries, "
    "back-and-forth mechanics. write tight prose, no headers, under 250 words."
)


async def _entity_refresh() -> None:
    await db.execute(
        """update entities e
           set seen_count = seen_count + sub.cnt,
               last_seen_at = now()
           from (
               select name, count(*) as cnt
               from entities ent
               join conversations c on c.body ilike '%' || ent.name || '%'
               where c.created_at > now() - interval '24 hours'
               group by name
           ) sub
           where e.name = sub.name"""
    )


async def _sessions_to_summarize() -> list[dict]:
    rows = await db.fetch(
        """select session_id, count(*) as turns, max(created_at) as last_at
           from conversations
           where role in ('user', 'assistant')
             and created_at < now() - make_interval(days => $1)
           group by session_id
           having count(*) >= 2
           order by max(created_at) asc
           limit $2""",
        SUMMARIZE_AFTER_DAYS, MAX_SESSIONS_PER_NIGHT,
    )
    return [dict(r) for r in rows]


async def _summarize_session(session_id) -> bool:
    turns = await db.fetch(
        """select role, body, created_at from conversations
           where session_id = $1 and role in ('user', 'assistant')
             and created_at < now() - make_interval(days => $2)
           order by created_at asc limit $3""",
        session_id, SUMMARIZE_AFTER_DAYS, MAX_TURNS_PER_SESSION,
    )
    if len(turns) < 2:
        return False

    transcript = "\n".join(f"{t['role']}: {t['body'][:1200]}" for t in turns)
    resp = await claude_client.message(
        model=settings.model_cheap,
        system=SUMMARY_PROMPT,
        messages=[{"role": "user", "content": transcript[:100_000]}],
        max_tokens=600,
        temperature=0.2,
    )
    summary = "".join(b.text for b in resp.content if b.type == "text").strip()
    if not summary:
        return False

    # embed for hybrid retrieval; summary is what future recall sees.
    embedding = None
    try:
        from api.memory.embeddings import embed
        embedding = await embed(summary)
    except Exception:
        log.warning("summary embedding failed, storing without", session=str(session_id))

    await db.execute(
        """insert into conversations (session_id, role, body, embedding, metadata)
           values ($1, 'summary', $2, $3, $4)""",
        session_id, summary,
        str(embedding) if embedding is not None else None,
        json.dumps({"kind": "consolidated", "turns": len(turns),
                    "span_end": turns[-1]["created_at"].isoformat()}),
    )
    await db.execute(
        """delete from conversations
           where session_id = $1 and role in ('user', 'assistant')
             and created_at < now() - make_interval(days => $2)""",
        session_id, SUMMARIZE_AFTER_DAYS,
    )
    return True


async def run() -> None:
    setup_logging()
    log.info("consolidating memory")
    budget.set_run("consolidate")

    await _entity_refresh()

    allowed, why = await budget.allow_run("consolidate")
    if not allowed:
        log.warning("consolidation summarization skipped", why=why)
    else:
        done = 0
        for s in await _sessions_to_summarize():
            try:
                if await _summarize_session(s["session_id"]):
                    done += 1
            except Exception:
                log.exception("session summarization failed", session=str(s["session_id"]))
        log.info("consolidation summarized sessions", count=done)

    # vacuum-style cleanup for very old, low-signal rows.
    await db.execute(
        "delete from conversations where created_at < now() - interval '180 days' and length(body) < 40 and role != 'summary'"
    )

    log.info("consolidation done")


if __name__ == "__main__":
    asyncio.run(run())
