"""nightly memory consolidation. promote frequent entities, summarize old conversations.

phase 2 fills this in. for now, runs the cleanup statements and exits.
"""

from __future__ import annotations

import asyncio

from api.memory.db import db
from api.observability.logging import log, setup_logging


async def run() -> None:
    setup_logging()
    log.info("consolidating memory")

    # touch entities last_seen if their name appears in recent conversations.
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

    # vacuum-style cleanup for very old, low-signal conversations.
    # phase 2 swaps this for actual summarization with claude.
    await db.execute(
        "delete from conversations where created_at < now() - interval '180 days' and length(body) < 40"
    )

    log.info("consolidation done")


if __name__ == "__main__":
    asyncio.run(run())
