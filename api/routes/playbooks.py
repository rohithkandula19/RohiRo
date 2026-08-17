"""playbook routes. list, read, save, delete, run."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api import playbooks as pb

router = APIRouter()


class PlaybookIn(BaseModel):
    body: str = Field(min_length=1, max_length=100_000)


@router.get("")
async def list_all() -> list[dict[str, Any]]:
    return pb.list_playbooks()


@router.get("/{name}")
async def get_one(name: str) -> dict[str, Any]:
    body = pb.get_playbook(name)
    if body is None:
        raise HTTPException(404, "playbook not found")
    return {"name": name, "body": body}


@router.put("/{name}")
async def save(name: str, payload: PlaybookIn) -> dict[str, Any]:
    try:
        pb.save_playbook(name, payload.body)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True, "name": name}


@router.delete("/{name}")
async def delete(name: str) -> dict[str, Any]:
    if not pb.delete_playbook(name):
        raise HTTPException(404, "playbook not found")
    return {"ok": True}


@router.post("/{name}/run")
async def run(name: str) -> dict[str, Any]:
    try:
        return await pb.run_playbook(name)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
