"""skills routes. browse the catalog, read one, run one on a task."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api import skills_bridge as sb

router = APIRouter()


class TaskIn(BaseModel):
    task: str = Field(min_length=3, max_length=8000)


@router.get("")
async def list_skills(q: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
    return await sb.catalog(query=q, limit=min(limit, 200))


@router.get("/{name:path}/body")
async def get_body(name: str) -> dict[str, Any]:
    body = await sb.load(name)
    if body is None:
        raise HTTPException(404, "no such skill")
    return {"name": name, "body": body}


@router.post("/{name:path}/run")
async def run(name: str, payload: TaskIn) -> dict[str, Any]:
    try:
        return await sb.run_skill(name, payload.task)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
