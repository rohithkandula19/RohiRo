"""browser trust tiers. standing rules that pre-approve boring actions.

the preferences key `browser_trust` maps a domain to a tier:

  read      — browser.render of pages on this domain runs without a card
  navigate  — render + goto on this domain run without a card

everything else — click, fill, scroll, close, and any domain not listed —
still stops at the approval gate. url-bearing actions only: an action
whose target domain cannot be read from its payload is never auto-run.
policy-approved rows land in action_log as approved (auditable) and their
sends still hit the egress ledger.
"""

from __future__ import annotations

import json
import time
from typing import Optional
from urllib.parse import urlparse

from api.memory.db import db

TRUST_KEY = "browser_trust"
_CACHE_TTL_S = 30
_cache: tuple[float, dict[str, str]] = (0.0, {})


async def rules() -> dict[str, str]:
    global _cache
    now = time.monotonic()
    if now - _cache[0] < _CACHE_TTL_S:
        return _cache[1]
    out: dict[str, str] = {}
    try:
        row = await db.fetchrow("select value from preferences where key = $1", TRUST_KEY)
        if row:
            value = row["value"]
            if isinstance(value, str):
                value = json.loads(value)
            if isinstance(value, dict):
                out = {
                    str(k).lower().lstrip("*."): str(v)
                    for k, v in value.items()
                    if str(v) in ("read", "navigate")
                }
    except Exception:
        out = {}
    _cache = (now, out)
    return out


def invalidate_cache() -> None:
    global _cache
    _cache = (0.0, {})


def _domain(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _tier_for(domain: str, table: dict[str, str]) -> Optional[str]:
    if not domain:
        return None
    for rule_domain, tier in table.items():
        if domain == rule_domain or domain.endswith("." + rule_domain):
            return tier
    return None


async def browser_auto(tool: str, url: Optional[str]) -> bool:
    """may this browser action run without a card? url-bearing only."""
    if not url:
        return False
    tier = _tier_for(_domain(url), await rules())
    if tier is None:
        return False
    if tool == "browser.render":
        return tier in ("read", "navigate")
    if tool == "browser.goto":
        return tier == "navigate"
    return False
