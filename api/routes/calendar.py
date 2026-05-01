"""calendar routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter

router = APIRouter()


@router.get("/week")
async def week() -> list[dict[str, Any]]:
    base = datetime.now(tz=timezone.utc).replace(hour=14, minute=0, second=0, microsecond=0)
    return [
        {
            "id": "evt-1",
            "title": "ml platform standup",
            "start": base.isoformat(),
            "end": (base + timedelta(minutes=25)).isoformat(),
            "attendees": ["alex@pnc.com", "priya@pnc.com"],
            "prep": "alex wanted to review the cache key change. pull the diff in.",
        },
        {
            "id": "evt-2",
            "title": "photon labs round 2",
            "start": (base + timedelta(days=1, hours=2)).isoformat(),
            "end": (base + timedelta(days=1, hours=3)).isoformat(),
            "attendees": ["sarah@photonlabs.com"],
            "prep": "system design, focus on retrieval. they pushed back on hybrid last time.",
        },
    ]


@router.get("/negotiations")
async def negotiations() -> list[dict[str, Any]]:
    return [
        {
            "id": "neg-1",
            "with": "sarah lin",
            "status": "waiting on reply",
            "last_action": "proposed tuesday 2 to 3:30 et",
        }
    ]
