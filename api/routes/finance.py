"""finance routes (plaid read-only)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter()


@router.get("/balances")
async def balances() -> list[dict[str, Any]]:
    return [
        {"id": "b-1", "name": "checking", "balance": 4218.40, "available": 4218.40},
        {"id": "b-2", "name": "savings", "balance": 22500.00, "available": 22500.00},
    ]


@router.get("/expenses")
async def expenses() -> list[dict[str, Any]]:
    return [
        {"category": "groceries", "total": 412.30},
        {"category": "rent", "total": 2100.00},
        {"category": "subscriptions", "total": 87.94},
        {"category": "eating out", "total": 198.40},
    ]


@router.get("/subscriptions")
async def subscriptions() -> list[dict[str, Any]]:
    return [
        {"id": "s-1", "name": "anthropic", "monthly": 20.00, "renews": "2026-05-12"},
        {"id": "s-2", "name": "github copilot", "monthly": 10.00, "renews": "2026-05-18"},
        {"id": "s-3", "name": "chatgpt plus", "monthly": 20.00, "renews": "2026-05-22"},
    ]


@router.get("/invoices")
async def invoices() -> list[dict[str, Any]]:
    return []
