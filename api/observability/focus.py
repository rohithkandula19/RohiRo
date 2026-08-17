"""focus-aware delivery. ro should not buzz you during do not disturb.

two signals decide whether a ping goes out. macos focus state, read
best-effort from the do not disturb assertions file. and quiet hours,
a preference like "22-08" that wraps midnight. urgent pings always go
through. everything else waits for a clear window.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from api.memory.db import db
from api.observability.logging import log

QUIET_KEY = "quiet_hours"

FOCUS_ASSERTIONS_PATH = Path.home() / "Library" / "DoNotDisturb" / "DB" / "Assertions.json"


def _read_macos_focus() -> Optional[str]:
    """best-effort read of the macos focus state. returns the active focus
    mode identifier, "focus" when active but unnamed, or None when no focus
    is active or anything at all goes wrong (missing file, permissions,
    malformed json)."""
    try:
        raw = FOCUS_ASSERTIONS_PATH.read_text()
        data = json.loads(raw)
        records = data["data"][0]["storeAssertionRecords"]
        if not records:
            return None
        try:
            mode = records[0]["assertionDetails"]["assertionDetailsModeIdentifier"]
            return str(mode) or "focus"
        except Exception:
            return "focus"
    except Exception:
        return None


def _quiet_hours_active(now_hour: int, spec: str) -> bool:
    """pure. spec is "HH-HH" in 24h local time, start inclusive, end
    exclusive. "22-08" wraps midnight. "" or malformed means never quiet."""
    spec = (spec or "").strip()
    if not spec:
        return False
    try:
        start_s, end_s = spec.split("-", 1)
        start, end = int(start_s), int(end_s)
    except Exception:
        return False
    if not (0 <= start <= 23 and 0 <= end <= 24):
        return False
    if start == end:
        return False
    if start < end:
        return start <= now_hour < end
    return now_hour >= start or now_hour < end


async def quiet_spec() -> str:
    """read the quiet hours spec from preferences. "" means never quiet."""
    row = await db.fetchrow("select value from preferences where key = $1", QUIET_KEY)
    if not row:
        return ""
    value = row["value"]
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            return value
    return value if isinstance(value, str) else ""


async def should_ping(urgent: bool = False) -> tuple[bool, str]:
    """may a notification go out right now? urgent always wins. focus and
    quiet hours defer everything else. fail open: an unreadable preference
    never silences an otherwise clear window."""
    if urgent:
        return True, "urgent"
    if _read_macos_focus() is not None:
        return False, "focus active"
    try:
        spec = await quiet_spec()
    except Exception as e:
        log.warning("quiet hours check failed, treating as clear", error=str(e))
        spec = ""
    if _quiet_hours_active(datetime.now().hour, spec):
        return False, "quiet hours"
    return True, "clear"


async def defer_note() -> str:
    """short line for logs describing the current delivery decision."""
    allowed, reason = await should_ping()
    if allowed:
        return "delivery clear"
    return f"delivery deferred: {reason}"
