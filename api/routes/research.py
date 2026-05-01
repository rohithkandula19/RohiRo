"""research routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter()


@router.get("/reading-list")
async def reading_list() -> list[dict[str, Any]]:
    return [
        {"id": "p-1", "title": "RAG without retrieval", "authors": "doe et al", "status": "queued"},
        {"id": "p-2", "title": "context distillation in long-context models", "authors": "kim et al", "status": "reading"},
    ]


@router.get("/search")
async def search(q: str = "") -> list[dict[str, Any]]:
    return [{"title": f"results for: {q}", "url": "", "snippet": "wired up in phase 5"}]
