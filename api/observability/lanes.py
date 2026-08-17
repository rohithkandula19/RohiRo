"""processing lanes. minimization by architecture, not by policy.

two mechanisms, one enforcement point:

- vault lane: sources tagged vault (a channel, a contact substring, an agent
  domain, an email address) are only ever processed by the local tier. the
  taint follows the data into memory: vault rows never surface in a
  cloud-bound prompt.
- airgap mode: a global switch. while on, every cloud model call raises
  instead of sending. the local tier keeps working. flip it in /settings or
  the menubar.

enforcement lives in the claude wrapper and the embeddings wrapper: when the
current lane forbids cloud, the call raises LaneViolation before any bytes
leave. callers choose their fallback (local model, or an honest "vault
content needs the local tier" message). policy is data; enforcement is code.
"""

from __future__ import annotations

import json
import time
from contextvars import ContextVar
from typing import Any, Optional

from api.memory.db import db
from api.observability.logging import log

current_lane: ContextVar[str] = ContextVar("ro_lane", default="cloud")

VAULT_RULES_KEY = "vault_rules"
AIRGAP_KEY = "airgap"
_CACHE_TTL_S = 30

_rules_cache: tuple[float, dict[str, Any]] = (0.0, {})
_airgap_cache: tuple[float, bool] = (0.0, False)


class LaneViolation(RuntimeError):
    """a cloud call was attempted from a lane that forbids it."""


def set_lane(lane: str):
    return current_lane.set(lane)


def get_lane() -> str:
    return current_lane.get()


async def _pref(key: str) -> Any:
    row = await db.fetchrow("select value from preferences where key = $1", key)
    if not row:
        return None
    value = row["value"]
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            pass
    return value


async def vault_rules() -> dict[str, list[str]]:
    """{channels: [], contacts: [], domains: [], addresses: []} — cached."""
    global _rules_cache
    now = time.monotonic()
    if now - _rules_cache[0] < _CACHE_TTL_S:
        return _rules_cache[1]
    raw = await _pref(VAULT_RULES_KEY) or {}
    rules = {
        "channels": [str(x).lower() for x in raw.get("channels", [])],
        "contacts": [str(x).lower() for x in raw.get("contacts", [])],
        "domains": [str(x).lower() for x in raw.get("domains", [])],
        "addresses": [str(x).lower() for x in raw.get("addresses", [])],
    }
    _rules_cache = (now, rules)
    return rules


async def airgap_on() -> bool:
    global _airgap_cache
    now = time.monotonic()
    if now - _airgap_cache[0] < _CACHE_TTL_S:
        return _airgap_cache[1]
    on = bool(await _pref(AIRGAP_KEY))
    _airgap_cache = (now, on)
    return on


def invalidate_cache() -> None:
    global _rules_cache, _airgap_cache
    _rules_cache = (0.0, {})
    _airgap_cache = (0.0, False)


async def lane_for_inbound(channel: str, chat_key: str, sender: str = "") -> str:
    """which lane does this inbound message belong to?"""
    rules = await vault_rules()
    if channel.lower() in rules["channels"]:
        return "vault"
    hay = f"{chat_key} {sender}".lower()
    for needle in rules["contacts"] + rules["addresses"]:
        if needle and needle in hay:
            return "vault"
    return "cloud"


async def lane_for_domain(domain: str) -> str:
    """agent domains (health, finance, ...) can be vault by rule."""
    rules = await vault_rules()
    return "vault" if domain.lower() in rules["domains"] else "cloud"


async def cloud_allowed() -> bool:
    """may this async context call a cloud model right now?"""
    if get_lane() == "vault":
        return False
    if await airgap_on():
        return False
    return True


async def check_cloud(call_kind: str) -> None:
    """raise LaneViolation if cloud calls are forbidden here. the wrappers
    call this before any bytes leave the machine."""
    if get_lane() == "vault":
        raise LaneViolation(f"vault lane: {call_kind} call refused, use the local tier")
    if await airgap_on():
        raise LaneViolation(f"airgap on: {call_kind} call refused, use the local tier")
