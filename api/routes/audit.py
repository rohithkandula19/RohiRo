"""audit routes. the egress ledger, mechanically verifiable."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from api.observability import ledger

router = APIRouter()


@router.get("")
async def list_recent() -> list[dict[str, Any]]:
    return await ledger.recent()


@router.get("/verify")
async def verify_chain() -> dict[str, Any]:
    return await ledger.verify()
