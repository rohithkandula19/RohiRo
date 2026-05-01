"""code routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter()


@router.get("/repos")
async def repos() -> list[dict[str, Any]]:
    return [
        {
            "name": "rohflow",
            "last_commit": "tighten retry policy on tool nodes",
            "ci": "green",
            "deploy": "live",
            "open_prs": 1,
        },
        {
            "name": "ro-job-bot",
            "last_commit": "fix recruiter intent classifier",
            "ci": "yellow",
            "deploy": "staging",
            "open_prs": 0,
        },
        {
            "name": "ro-medrag",
            "last_commit": "ablate query rewriter",
            "ci": "green",
            "deploy": "n/a",
            "open_prs": 2,
        },
    ]


@router.get("/issues")
async def issues() -> list[dict[str, Any]]:
    return [
        {"repo": "rohflow", "number": 42, "title": "tool retry on rate limit", "status": "open"},
        {"repo": "ro-medrag", "number": 8, "title": "evaluate hybrid retrieval on medqa", "status": "open"},
    ]
