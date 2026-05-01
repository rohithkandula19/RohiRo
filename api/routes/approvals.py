"""approval routes. list pending, decide, mark executed."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.supervisor import approval

router = APIRouter()


class Decision(BaseModel):
    decision: str  # approved | rejected | edited
    edit_note: Optional[str] = None


@router.get("")
async def list_pending() -> list[dict]:
    return await approval.list_pending()


@router.post("/{action_id}/decide")
async def decide(action_id: str, payload: Decision) -> dict:
    try:
        aid = uuid.UUID(action_id)
    except ValueError as e:
        raise HTTPException(400, "bad id") from e
    await approval.decide(aid, decision=payload.decision, edit_note=payload.edit_note)
    return {"ok": True}
