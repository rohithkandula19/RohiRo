"""eval routes: stats, learned voice, manual triggers."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from api.eval import stats as stats_mod
from api.eval import voice_learner

router = APIRouter()


@router.get("/stats")
async def get_stats(days: int = 7) -> dict[str, Any]:
    return await stats_mod.recent_stats(days=days)


@router.get("/rejections")
async def get_rejections(limit: int = 5) -> list[dict[str, Any]]:
    return await stats_mod.rejection_examples(limit=limit)


@router.get("/streak")
async def get_streak(channel: str = "gmail", limit: int = 20) -> list[dict[str, Any]]:
    return await stats_mod.edit_streak(channel=channel, limit=limit)


class VoiceOut(BaseModel):
    channel: str
    rules_md: str


@router.get("/voice", response_model=list[VoiceOut])
async def list_voice() -> list[VoiceOut]:
    from api.memory.db import db
    rows = await db.fetch(
        "select channel, rules_md from learned_voice order by updated_at desc"
    )
    return [VoiceOut(channel=r["channel"], rules_md=r["rules_md"] or "") for r in rows]


@router.post("/voice/relearn")
async def relearn_voice() -> dict[str, Any]:
    """trigger the voice learner manually. hourly background also runs it."""
    return await voice_learner.learn_voice()
