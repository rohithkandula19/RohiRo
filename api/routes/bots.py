"""crew routes. hire, brief, run, and watch your named ro's."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api import crew

router = APIRouter()


class CharterIn(BaseModel):
    body: str = Field(min_length=1, max_length=50_000)


class TaskIn(BaseModel):
    task: str = Field(min_length=3, max_length=8000)


class DraftIn(BaseModel):
    role: str = Field(min_length=10, max_length=4000)


@router.get("")
async def list_all() -> list[dict[str, Any]]:
    return crew.list_bots()


@router.get("/messages")
async def messages(limit: int = 100) -> list[dict[str, Any]]:
    from api.memory.db import db
    rows = await db.fetch(
        "select from_bot, to_bot, body, created_at from bot_messages order by id desc limit $1",
        min(limit, 300),
    )
    return [
        {"from": r["from_bot"], "to": r["to_bot"], "body": r["body"][:500],
         "at": r["created_at"].isoformat()}
        for r in rows
    ]


@router.get("/{name}")
async def get_one(name: str) -> dict[str, Any]:
    body = crew.get_charter(name)
    if body is None:
        raise HTTPException(404, "no such bot")
    return {"name": name, "charter": body}


@router.put("/{name}")
async def save(name: str, payload: CharterIn) -> dict[str, Any]:
    try:
        crew.save_charter(name, payload.body)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True, "name": name}


@router.delete("/{name}")
async def remove(name: str) -> dict[str, Any]:
    if not crew.delete_bot(name):
        raise HTTPException(404, "no such bot")
    return {"ok": True}


@router.post("/{name}/run")
async def run_one(name: str, payload: TaskIn) -> dict[str, Any]:
    try:
        return await crew.run_bot(name, payload.task)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/crew/run")
async def run_all(payload: TaskIn) -> dict[str, Any]:
    return await crew.run_crew(payload.task)


DRAFT_SYSTEM = (
    "you write charters for named bots on a personal agent crew. a charter "
    "is markdown: `# <name>` line, a one-line mission, `## owns` (their "
    "lane), `## how i work` (method, tone, when to delegate with the "
    "'>> bot: task' syntax), `## never` (boundaries). under 250 words, "
    "lowercase, concrete. never instruct bypassing approvals."
)


@router.post("/draft")
async def draft(payload: DraftIn) -> dict[str, Any]:
    """hire by description: say the role, get a charter to review."""
    from api.config import settings as cfg
    from api.observability import budget
    from api.observability.claude import claude_client

    budget.set_run("bot:draft")
    resp = await claude_client.message(
        model=cfg.model_cheap,
        system=DRAFT_SYSTEM,
        messages=[{"role": "user", "content": f"write a charter for this role:\n\n{payload.role}"}],
        max_tokens=700,
        temperature=0.3,
    )
    body = "".join(b.text for b in resp.content if b.type == "text").strip()
    if not body:
        raise HTTPException(502, "draft came back empty")
    return {"charter": body}
