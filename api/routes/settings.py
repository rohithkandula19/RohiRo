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


@router.get("/mcp")
async def get_mcp() -> dict[str, Any]:
    """configured mcp servers and their tools (or their connection error)."""
    from api.integrations import mcp_host
    if not mcp_host.configured():
        return {"configured": False, "hint": "copy mcp_servers.example.json to mcp_servers.json"}
    return {"configured": True, "servers": await mcp_host.list_all_tools()}


@router.get("/spend")
async def get_spend() -> dict[str, Any]:
    """today's claude spend, total and per run label, plus the daily cap."""
    from api.memory.db import db
    total = await budget.spent_today()
    cap_row = await db.fetchrow("select value from preferences where key = $1", budget.BUDGET_KEY)
    cap = cap_row["value"] if cap_row else None
    return {"today": total, "by_run": await budget.by_run_today(), "daily_cap": cap}


class AirgapIn(BaseModel):
    on: bool


class VaultRulesIn(BaseModel):
    channels: list[str] = []
    contacts: list[str] = []
    domains: list[str] = []
    addresses: list[str] = []


@router.get("/lanes")
async def get_lanes() -> dict[str, Any]:
    from api.observability import lanes
    return {"airgap": await lanes.airgap_on(), "vault_rules": await lanes.vault_rules()}


@router.post("/lanes/airgap")
async def set_airgap(payload: AirgapIn) -> dict[str, Any]:
    import json as _json
    from api.memory.db import db
    from api.observability import lanes
    await db.execute(
        """insert into preferences (key, value) values ($1, $2)
           on conflict (key) do update set value = excluded.value, updated_at = now()""",
        lanes.AIRGAP_KEY, _json.dumps(bool(payload.on)),
    )
    lanes.invalidate_cache()
    return {"ok": True, "airgap": payload.on}


@router.post("/lanes/vault")
async def set_vault_rules(payload: VaultRulesIn) -> dict[str, Any]:
    import json as _json
    from api.memory.db import db
    from api.observability import lanes
    await db.execute(
        """insert into preferences (key, value) values ($1, $2)
           on conflict (key) do update set value = excluded.value, updated_at = now()""",
        lanes.VAULT_RULES_KEY, _json.dumps(payload.model_dump()),
    )
    lanes.invalidate_cache()
    return {"ok": True, "vault_rules": payload.model_dump()}


class TrustIn(BaseModel):
    rules: dict[str, str]  # {domain: "read"|"navigate"}


@router.get("/trust")
async def get_trust() -> dict[str, Any]:
    from api.observability import trust
    return {"browser_trust": await trust.rules()}


@router.post("/trust")
async def set_trust(payload: TrustIn) -> dict[str, Any]:
    import json as _json
    from api.memory.db import db
    from api.observability import trust
    clean = {k.lower(): v for k, v in payload.rules.items() if v in ("read", "navigate")}
    await db.execute(
        """insert into preferences (key, value) values ($1, $2)
           on conflict (key) do update set value = excluded.value, updated_at = now()""",
        trust.TRUST_KEY, _json.dumps(clean),
    )
    trust.invalidate_cache()
    return {"ok": True, "browser_trust": clean}


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
