"""liveness heartbeats. silent breakage becomes visible red.

each background worker and integration beats after every attempt, ok or not.
/settings surfaces the table: green if the last beat was ok and recent, red
otherwise. a listener that stopped beating shows stale, which is the point.
"""

from __future__ import annotations

from typing import Any

from api.memory.db import db
from api.observability.logging import log


async def beat(name: str, *, ok: bool, error: str = "") -> None:
    """record a heartbeat. never raises."""
    try:
        await db.execute(
            """insert into heartbeats (name, ok, error, beat_at)
               values ($1, $2, $3, now())
               on conflict (name) do update
               set ok = excluded.ok, error = excluded.error, beat_at = excluded.beat_at""",
            name, ok, (error or "")[:500],
        )
    except Exception:
        log.warning("heartbeat write failed", name=name)


async def all_beats() -> list[dict[str, Any]]:
    try:
        rows = await db.fetch(
            "select name, ok, error, beat_at from heartbeats order by name asc"
        )
        return [
            {
                "name": r["name"],
                "ok": r["ok"],
                "error": r["error"],
                "beat_at": r["beat_at"].isoformat() if r["beat_at"] else None,
            }
            for r in rows
        ]
    except Exception:
        return []
