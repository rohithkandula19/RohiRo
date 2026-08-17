"""web push routes. subscribe from the web ui, test ping."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from api.integrations import webpush

router = APIRouter()


@router.get("/vapid-public")
async def vapid_public() -> dict[str, str]:
    if not webpush.configured():
        raise HTTPException(
            503,
            "push not configured. run: uv run python -m api.integrations.webpush --generate",
        )
    return {"key": webpush.public_key()}


@router.post("/subscribe")
async def subscribe(subscription: dict[str, Any]) -> dict[str, bool]:
    try:
        await webpush.save_subscription(subscription)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True}


@router.post("/test")
async def test_push() -> dict[str, int]:
    return await webpush.push_all(title="ro", body="push works.", url="/overview")
