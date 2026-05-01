"""settings routes. integrations, models, keys (last 4 only), backup."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from api.config import secrets, settings

router = APIRouter()


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
