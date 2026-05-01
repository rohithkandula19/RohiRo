"""files routes."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter

router = APIRouter()


@router.get("/recent")
async def recent(source: Optional[str] = None) -> list[dict[str, Any]]:
    rows = [
        {"id": "f-1", "name": "rohflow-architecture.md", "source": "drive", "modified": "2026-04-29"},
        {"id": "f-2", "name": "interview-notes.md", "source": "notion", "modified": "2026-04-30"},
        {"id": "f-3", "name": "~/code/ro-medrag/README.md", "source": "local", "modified": "2026-05-01"},
    ]
    if source and source != "all":
        rows = [r for r in rows if r["source"] == source]
    return rows
