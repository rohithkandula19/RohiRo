"""budget guard. per-run token accounting and a daily kill switch.

- every claude call records its tokens into spend_log, attributed to the
  current run label (a contextvar set by whoever started the work: the
  scheduler, the gateway, a playbook, or plain chat).
- the scheduler asks allow_run() before claiming a routine. over budget
  means no new background runs until tomorrow. user-initiated chat is never
  blocked; the budget protects against runaway automation, not against you.
- the cap lives in the preferences table under 'daily_token_budget'
  (integer tokens per day, 0 or missing = no cap). fail closed: if the db
  read errors, background runs are refused.
"""

from __future__ import annotations

import json
from contextvars import ContextVar
from typing import Any, Optional

from api.memory.db import db
from api.observability.logging import log

current_run: ContextVar[str] = ContextVar("ro_current_run", default="chat")

BUDGET_KEY = "daily_token_budget"


def set_run(label: str):
    """set the attribution label for this async context. returns the token so
    callers can reset, though letting it scope out is fine for task-local use."""
    return current_run.set(label[:120])


async def record_usage(*, model: str, input_tokens: int, output_tokens: int) -> None:
    """called by the claude wrapper after every response. never raises."""
    try:
        await db.execute(
            """insert into spend_log (run_label, model, input_tokens, output_tokens)
               values ($1, $2, $3, $4)""",
            current_run.get(), model, int(input_tokens or 0), int(output_tokens or 0),
        )
    except Exception:
        log.warning("spend_log write failed", model=model)


async def _cap() -> Optional[int]:
    row = await db.fetchrow("select value from preferences where key = $1", BUDGET_KEY)
    if not row:
        return None
    value = row["value"]
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            return None
    try:
        cap = int(value)
    except (TypeError, ValueError):
        return None
    return cap if cap > 0 else None


async def spent_today() -> dict[str, Any]:
    row = await db.fetchrow(
        """select coalesce(sum(input_tokens + output_tokens), 0) as tokens,
                  count(*) as calls
           from spend_log where created_at >= date_trunc('day', now())"""
    )
    return {"tokens": int(row["tokens"]), "calls": int(row["calls"])}


async def by_run_today() -> list[dict[str, Any]]:
    rows = await db.fetch(
        """select run_label, sum(input_tokens + output_tokens) as tokens, count(*) as calls
           from spend_log where created_at >= date_trunc('day', now())
           group by run_label order by tokens desc limit 50"""
    )
    return [dict(r) for r in rows]


async def allow_run(kind: str = "routine") -> tuple[bool, str]:
    """may a background run start? fail closed on db errors."""
    try:
        cap = await _cap()
        if cap is None:
            return True, "no budget set"
        spent = (await spent_today())["tokens"]
        if spent >= cap:
            return False, f"daily budget spent: {spent}/{cap} tokens"
        return True, f"{spent}/{cap} tokens"
    except Exception as e:
        log.warning("budget check failed, refusing background run", kind=kind, error=str(e))
        return False, f"budget check unavailable: {e}"
