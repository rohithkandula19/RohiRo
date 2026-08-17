"""event triggers. when an inbound event matches, run a playbook.

the gateway calls match() on every inbound message. matches fire their
playbooks as background tasks (budget-checked inside run_playbook), so the
conversational reply is never delayed by trigger work. a per-trigger
cooldown stops one noisy thread from firing the same playbook in a loop.

pattern is a case-insensitive substring, or a regex when wrapped in
slashes: /invoice #\\d+/.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from typing import Any, Optional

from api.memory.db import db
from api.observability.logging import log

COOLDOWN_MINUTES = 10


def _matches(pattern: str, text: str) -> bool:
    p = pattern.strip()
    if len(p) > 2 and p.startswith("/") and p.endswith("/"):
        try:
            return re.search(p[1:-1], text, re.IGNORECASE) is not None
        except re.error:
            return False
    return p.lower() in text.lower()


async def list_triggers() -> list[dict[str, Any]]:
    rows = await db.fetch(
        """select id::text, channel, pattern, playbook, enabled,
                  last_fired_at, fire_count, created_at
           from triggers order by created_at desc"""
    )
    out = []
    for r in rows:
        d = dict(r)
        d["last_fired_at"] = r["last_fired_at"].isoformat() if r["last_fired_at"] else None
        d["created_at"] = r["created_at"].isoformat()
        out.append(d)
    return out


async def create_trigger(*, channel: str, pattern: str, playbook: str) -> str:
    from api.playbooks import get_playbook
    if get_playbook(playbook) is None:
        raise ValueError(f"playbook not found: {playbook}")
    if not pattern.strip():
        raise ValueError("pattern is empty")
    row = await db.fetchrow(
        """insert into triggers (channel, pattern, playbook)
           values ($1, $2, $3) returning id::text""",
        channel.strip() or "*", pattern.strip(), playbook.strip(),
    )
    return row["id"]


async def delete_trigger(trigger_id: str) -> bool:
    row = await db.fetchrow(
        "delete from triggers where id = $1 returning id", uuid.UUID(trigger_id)
    )
    return row is not None


async def set_enabled(trigger_id: str, enabled: bool) -> None:
    await db.execute(
        "update triggers set enabled = $2 where id = $1", uuid.UUID(trigger_id), enabled
    )


async def match_and_fire(channel: str, text: str) -> int:
    """called by the gateway on every inbound. fires matching playbooks in
    the background, returns how many fired. never raises."""
    try:
        rows = await db.fetch(
            """select id, pattern, playbook from triggers
               where enabled and (channel = $1 or channel = '*')
                 and (last_fired_at is null
                      or last_fired_at < now() - make_interval(mins => $2))""",
            channel, COOLDOWN_MINUTES,
        )
    except Exception:
        log.warning("trigger lookup failed", channel=channel)
        return 0

    try:
        from api.listeners import commands
        if await commands.is_paused():
            return 0
    except Exception:
        pass

    fired = 0
    for r in rows:
        if not _matches(r["pattern"], text):
            continue
        # claim the cooldown first so a burst can't double-fire
        claimed = await db.fetchrow(
            """update triggers set last_fired_at = now(), fire_count = fire_count + 1
               where id = $1 and (last_fired_at is null
                     or last_fired_at < now() - make_interval(mins => $2))
               returning id""",
            r["id"], COOLDOWN_MINUTES,
        )
        if claimed is None:
            continue
        fired += 1
        log.info("trigger fired", playbook=r["playbook"], channel=channel)
        asyncio.get_running_loop().create_task(_run(r["playbook"]))
    return fired


async def _run(name: str) -> None:
    try:
        from api.playbooks import run_playbook
        await run_playbook(name)
    except Exception:
        log.exception("triggered playbook failed", playbook=name)
