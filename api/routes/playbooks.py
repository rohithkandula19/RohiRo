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


@router.post("/{name}/shadow")
async def shadow(name: str) -> dict[str, Any]:
    """dry run: real supervisor, zero egress. every outward action lands as
    a simulated card so you can review the tape before arming it."""
    try:
        return await pb.run_playbook(name, shadow=True)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


class DraftIn(BaseModel):
    description: str = Field(min_length=10, max_length=8000)


DRAFT_SYSTEM = (
    "you write ro playbooks: markdown instructions a personal agent runs "
    "verbatim through its supervisor. structure: a `# title` line, then one "
    "or more `## step <name>` sections. each step is a clear instruction in "
    "second person ('check my calendar...'). steps see a digest of the "
    "previous step's output. rules: never instruct bypassing approvals, "
    "never invent credentials, keep it under 400 words, no preamble outside "
    "the playbook itself. write in lowercase, short sentences."
)


@router.post("/draft")
async def draft(payload: DraftIn) -> dict[str, Any]:
    """teach by description: narrate the task, claude writes the playbook.
    nothing is saved; the draft comes back for review in the editor."""
    from api.config import settings as cfg
    from api.observability import budget
    from api.observability.claude import claude_client

    budget.set_run("playbook:draft")
    resp = await claude_client.message(
        model=cfg.model_cheap,
        system=DRAFT_SYSTEM,
        messages=[{"role": "user", "content": (
            "write a playbook for this task, exactly as i described it:\n\n"
            + payload.description
        )}],
        max_tokens=900,
        temperature=0.3,
    )
    body = "".join(b.text for b in resp.content if b.type == "text").strip()
    if not body:
        raise HTTPException(502, "draft came back empty, try rephrasing")
    return {"body": body}
