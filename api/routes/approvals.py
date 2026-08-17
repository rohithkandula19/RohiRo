"""approval routes. list pending, decide, execute.

decide is compare-and-swap: only a pending action can be decided, and a
decided (approved or edited) action is executed exactly once via an atomic
claim. deciding an already decided action returns 409 with the current
status instead of double-sending.
"""

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

    outcome = await approval.decide(aid, decision=payload.decision, edit_note=payload.edit_note)

    if outcome == "not_found":
        raise HTTPException(404, "action not found")
    if outcome != "applied":
        # already decided or executed. no double-apply, no double-send.
        raise HTTPException(409, f"action already decided: {outcome.removeprefix('already_')}")

    # approved and edited both execute, exactly once (atomic claim inside).
    if payload.decision in {"approved", "edited"}:
        result = await execute_mod.execute(aid)
        return {"ok": True, "executed": True, "result": result}
    return {"ok": True, "executed": False}


@router.post("/{action_id}/execute")
async def execute_decided(action_id: str) -> dict:
    """re-drive a decided-but-unexecuted action (crash between decide and
    execute). the atomic claim makes this safe to call any number of times."""
    try:
        aid = uuid.UUID(action_id)
    except ValueError as e:
        raise HTTPException(400, "bad id") from e
    result = await execute_mod.execute(aid)
    return {"ok": result.get("ok", False), "result": result}
