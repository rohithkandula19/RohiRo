"""self-eval stats — approve/reject/edit counts, recent rejections, edit streaks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from api.memory.db import db


async def recent_stats(*, days: int = 7) -> dict[str, Any]:
    since = datetime.now(tz=timezone.utc) - timedelta(days=days)
    rows = await db.fetch(
        """select status, count(*) as n
           from action_log
           where created_at >= $1
           group by status""",
        since,
    )
    counts = {r["status"]: r["n"] for r in rows}
    total = sum(counts.values())
    approved = counts.get("executed", 0) + counts.get("approved", 0)
    edited = counts.get("edited", 0)
    rejected = counts.get("rejected", 0)
    failed = counts.get("failed", 0)

    approve_rate = (approved / total) if total else 0.0
    edit_rate = (edited / total) if total else 0.0
    reject_rate = (rejected / total) if total else 0.0

    # per-tool breakdown
    per_tool = await db.fetch(
        """select tool, status, count(*) as n
           from action_log
           where created_at >= $1
           group by tool, status
           order by tool""",
        since,
    )
    tools: dict[str, dict[str, int]] = {}
    for r in per_tool:
        tools.setdefault(r["tool"], {})[r["status"]] = r["n"]

    return {
        "window_days": days,
        "total": total,
        "approved": approved,
        "edited": edited,
        "rejected": rejected,
        "failed": failed,
        "approve_rate": round(approve_rate, 3),
        "edit_rate": round(edit_rate, 3),
        "reject_rate": round(reject_rate, 3),
        "per_tool": tools,
    }


async def edit_streak(channel: str = "gmail", *, limit: int = 20) -> list[dict[str, Any]]:
    """latest decisions on this channel — useful for "is ro getting better"."""
    rows = await db.fetch(
        """select decision, length(coalesce(edited, '')) as edit_len,
                  length(coalesce(original, '')) as orig_len, created_at
           from voice_signals
           where channel = $1
           order by created_at desc
           limit $2""",
        channel, limit,
    )
    return [dict(r, created_at=r["created_at"].isoformat()) for r in rows]


async def rejection_examples(*, limit: int = 5) -> list[dict[str, Any]]:
    rows = await db.fetch(
        """select tool, original, created_at
           from voice_signals
           where decision = 'rejected' and original <> ''
           order by created_at desc
           limit $1""",
        limit,
    )
    return [
        {"tool": r["tool"], "draft": r["original"][:240], "at": r["created_at"].isoformat()}
        for r in rows
    ]
