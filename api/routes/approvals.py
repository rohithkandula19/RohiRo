"""approval routes. list pending, decide, execute."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.supervisor import approval, execute as execute_mod

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

    # if approved (or edited), execute immediately
    if payload.decision in {"approved", "edited"}:
        result = await execute_mod.execute(aid)
        return {"ok": True, "executed": True, "result": result}
    return {"ok": True, "executed": False}
