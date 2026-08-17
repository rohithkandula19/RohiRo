"""settings routes. integrations, models, keys (last 4 only), backup."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from api.config import secrets, settings
from api.observability import budget, liveness

router = APIRouter()


@router.get("/liveness")
async def get_liveness() -> list[dict[str, Any]]:
    """last heartbeat per background worker. stale or not-ok shows red in the ui."""
    return await liveness.all_beats()


@router.get("/spend")
async def get_spend() -> dict[str, Any]:
    """today's claude spend, total and per run label, plus the daily cap."""
    from api.memory.db import db
    total = await budget.spent_today()
    cap_row = await db.fetchrow("select value from preferences where key = $1", budget.BUDGET_KEY)
    cap = cap_row["value"] if cap_row else None
    return {"today": total, "by_run": await budget.by_run_today(), "daily_cap": cap}


class BudgetIn(BaseModel):
    daily_token_budget: int


@router.post("/spend/budget")
async def set_budget(payload: BudgetIn) -> dict[str, Any]:
    from api.memory.db import db
    import json as _json
    await db.execute(
        """insert into preferences (key, value) values ($1, $2)
           on conflict (key) do update set value = excluded.value, updated_at = now()""",
        budget.BUDGET_KEY, _json.dumps(int(payload.daily_token_budget)),
    )
    return {"ok": True, "daily_token_budget": payload.daily_token_budget}


INTEGRATIONS = [
    "gmail", "google_calendar", "google_drive", "github", "slack",
    "notion", "linear", "imessage", "telegram", "whatsapp",
    "linkedin", "twitter", "instagram", "plaid", "strava", "apple_health",
]


class ModelConfig(BaseModel):
    default: str
    hard: str
    cheap: str


def _last4(name: str) -> dict[str, Any]:
    val = secrets.get(name)
    if not val:
        return {"name": name, "configured": False, "last4": ""}
    tail = val[-4:] if len(val) >= 4 else "****"
    return {"name": name, "configured": True, "last4": tail}


@router.get("/integrations")
async def list_integrations() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "connected": _is_connected(name),
            "tier": _tier_for(name),
            "last_sync": None,
        }
        for name in INTEGRATIONS
    ]


@router.get("/keys")
async def list_keys() -> list[dict[str, Any]]:
    return [
        _last4(k)
        for k in [
            "anthropic_api_key", "openai_api_key", "github_token",
            "slack_bot_token", "notion_token", "linear_api_key",
            "plaid_client_id", "plaid_secret", "telegram_bot_token",
            "strava_client_id", "strava_client_secret",
            "gcs_bucket", "vapid_public_key", "vapid_private_key",
        ]
    ]


@router.get("/models")
async def get_models() -> ModelConfig:
    return ModelConfig(
        default=settings.model_default,
        hard=settings.model_hard,
        cheap=settings.model_cheap,
    )


def _is_connected(name: str) -> bool:
    mapping = {
        "github": "github_token",
        "slack": "slack_bot_token",
        "notion": "notion_token",
        "linear": "linear_api_key",
        "plaid": "plaid_client_id",
        "telegram": "telegram_bot_token",
        "strava": "strava_client_id",
    }
    if name in mapping:
        return bool(secrets.get(mapping[name]))
    return False


def _tier_for(name: str) -> int:
    if name in {"whatsapp", "linkedin", "twitter", "instagram"}:
        return 2
    return 1
