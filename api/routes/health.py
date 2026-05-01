"""health routes (apple health, strava)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter()


@router.get("/today")
async def today() -> dict[str, Any]:
    return {
        "steps": 6420,
        "sleep_hours": 7.1,
        "resting_hr": 56,
        "weekly_active_minutes": 213,
        "weekly_goal": 300,
    }


@router.get("/workouts")
async def workouts() -> list[dict[str, Any]]:
    return [
        {"id": "w-1", "kind": "run", "distance_km": 7.4, "minutes": 38, "date": "2026-04-30"},
        {"id": "w-2", "kind": "lift", "minutes": 45, "date": "2026-04-29"},
    ]
