"""schedule routes: list / create / delete / run-now."""

from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.scheduler import (
    create as schedule_create,
    delete as schedule_delete,
    fire as schedule_fire,
    list_all,
)

router = APIRouter()


class ScheduleIn(BaseModel):
    kind: str
    spec: str
    text: str
    title: Optional[str] = ""
    timezone: Optional[str] = "UTC"


@router.get("")
async def get_all() -> list[dict[str, Any]]:
    items = await list_all()
    return [s.__dict__ for s in items]


@router.post("")
async def create_one(payload: ScheduleIn) -> dict[str, Any]:
    sid = await schedule_create(
        kind=payload.kind,
        spec=payload.spec,
        text=payload.text,
        title=payload.title or "",
        tz=payload.timezone or "UTC",
    )
    return {"id": sid}


@router.delete("/{schedule_id}")
async def delete_one(schedule_id: str) -> dict[str, Any]:
    try:
        uuid.UUID(schedule_id)
    except ValueError as e:
        raise HTTPException(400, "bad id") from e
    ok = await schedule_delete(schedule_id)
    return {"deleted": ok}


@router.post("/{schedule_id}/run")
async def run_now(schedule_id: str) -> dict[str, Any]:
    items = await list_all()
    s = next((x for x in items if x.id == schedule_id), None)
    if s is None:
        raise HTTPException(404, "schedule not found")
    return await schedule_fire(s)
