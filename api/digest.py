"""daily digest. runs at 7am via launchd.

drafts a short summary of yesterday: completed actions, pending approvals,
errors, token spend. puts it in the inbox as a draft email to ro.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from api.memory.db import db
from api.observability.claude import claude_client
from api.observability.logging import log, setup_logging


async def run() -> None:
    setup_logging()
    since = datetime.now(tz=timezone.utc) - timedelta(hours=24)

    completed = await db.fetch(
        "select tool, description, executed_at from action_log "
        "where status = 'executed' and executed_at >= $1 order by executed_at desc",
        since,
    )
    pending = await db.fetch(
        "select tool, description, created_at from action_log where status = 'pending'"
    )
    errors = await db.fetch(
        "select tool, error, created_at from action_log where status = 'failed' and created_at >= $1",
        since,
    )

    log.info("digest", completed=len(completed), pending=len(pending), errors=len(errors))

    body = _format(completed, pending, errors)
    print(body)  # launchd captures stdout to /tmp/ro.digest.out.log


def _format(completed: list, pending: list, errors: list) -> str:
    lines = ["# yesterday with ro\n"]
    lines.append(f"completed: {len(completed)}")
    lines.append(f"pending: {len(pending)}")
    lines.append(f"errors: {len(errors)}\n")
    if pending:
        lines.append("## waiting on you")
        for p in pending[:5]:
            lines.append(f"- {p['tool']}: {p['description']}")
    return "\n".join(lines)


if __name__ == "__main__":
    asyncio.run(run())
