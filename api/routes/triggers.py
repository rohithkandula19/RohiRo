"""trigger routes. when X arrives, run playbook Y."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api import triggers as trig

router = APIRouter()


class TriggerIn(BaseModel):
    channel: str = Field(default="*", max_length=32)
    pattern: str = Field(min_length=1, max_length=500)
    playbook: str = Field(min_length=1, max_length=64)


class EnabledIn(BaseModel):
    enabled: bool


@router.get("")
async def list_all() -> list[dict[str, Any]]:
    return await trig.list_triggers()


@router.post("")
async def create(payload: TriggerIn) -> dict[str, Any]:
    try:
        tid = await trig.create_trigger(
            channel=payload.channel, pattern=payload.pattern, playbook=payload.playbook,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True, "id": tid}


@router.post("/{trigger_id}/enabled")
async def toggle(trigger_id: str, payload: EnabledIn) -> dict[str, Any]:
    await trig.set_enabled(trigger_id, payload.enabled)
    return {"ok": True}


@router.delete("/{trigger_id}")
async def delete(trigger_id: str) -> dict[str, Any]:
    if not await trig.delete_trigger(trigger_id):
        raise HTTPException(404, "trigger not found")
    return {"ok": True}
