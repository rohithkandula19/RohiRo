"""jobs routes. wraps ro job bot in phase 5."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter()


@router.get("/applications")
async def applications() -> dict[str, list[dict[str, Any]]]:
    cols = {
        "applied": [],
        "screen": [
            {"id": "app-1", "company": "photon labs", "role": "staff ml", "score": 0.84, "next": "round 2 tuesday"},
        ],
        "onsite": [],
        "offer": [],
        "rejected": [],
    }
    return cols


@router.get("/recruiters")
async def recruiters() -> list[dict[str, Any]]:
    return [
        {"id": "rec-1", "name": "sarah lin", "company": "photon labs", "last_message": "round 2 invite"},
    ]
