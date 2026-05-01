"""inbox routes. unified message feed across sources.

phase 3 wires real gmail. for now, returns whatever the comms agent has
queued plus a small set of placeholder rows so the ui works in dev.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter

router = APIRouter()


def _stub() -> list[dict[str, Any]]:
    now = datetime.now(tz=timezone.utc)
    return [
        {
            "id": "stub-1",
            "source": "gmail",
            "from_name": "sarah lin",
            "from_handle": "sarah@photonlabs.com",
            "subject": "follow up on the screen",
            "snippet": "thanks for the time on tuesday. wanted to send over the next steps...",
            "received_at": (now - timedelta(hours=2)).isoformat(),
            "unread": True,
            "has_draft": True,
        },
        {
            "id": "stub-2",
            "source": "slack",
            "from_name": "#ml-platform",
            "from_handle": "alex chen",
            "subject": "thread: model gateway rollout",
            "snippet": "ro can you double-check the cache key format we landed on?",
            "received_at": (now - timedelta(hours=5)).isoformat(),
            "unread": True,
            "has_draft": False,
        },
        {
            "id": "stub-3",
            "source": "imessage",
            "from_name": "mom",
            "from_handle": "+1...",
            "subject": "",
            "snippet": "are you home for the long weekend?",
            "received_at": (now - timedelta(hours=22)).isoformat(),
            "unread": False,
            "has_draft": False,
        },
    ]


@router.get("")
async def inbox(source: Optional[str] = None, unread_only: bool = False) -> list[dict[str, Any]]:
    rows = _stub()
    if source and source != "all":
        rows = [r for r in rows if r["source"] == source]
    if unread_only:
        rows = [r for r in rows if r["unread"]]
    return rows


@router.get("/{message_id}")
async def thread(message_id: str) -> dict[str, Any]:
    return {
        "id": message_id,
        "source": "gmail",
        "subject": "follow up on the screen",
        "messages": [
            {"role": "them", "body": "thanks for the time on tuesday. wanted to send over the next steps. when works for round 2?"},
        ],
        "draft": "tuesday afternoon works. i'll block 2 to 3:30 et and send a calendar hold.",
    }
