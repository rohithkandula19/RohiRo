"""approval store. supervisor pauses, posts to action_log, resumes when ro decides."""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from api.memory.db import db


async def open_approval(
    *,
    session_id: uuid.UUID,
    domain: str,
    tool: str,
    description: str,
    payload: dict[str, Any],
    requires_approval: bool = True,
) -> uuid.UUID:
    row = await db.fetchrow(
        """insert into action_log (session_id, domain, tool, description, payload, requires_approval)
           values ($1, $2, $3, $4, $5, $6) returning id""",
        session_id,
        domain,
        tool,
        description,
        json.dumps(payload),
        requires_approval,
    )
    return row["id"]


async def list_pending() -> list[dict[str, Any]]:
    rows = await db.fetch(
        "select id::text, session_id::text, domain, tool, description, payload, created_at "
        "from action_log where status = 'pending' order by created_at asc"
    )
    out = []
    for r in rows:
        d = dict(r)
        if isinstance(d.get("payload"), str):
            try:
                d["payload"] = json.loads(d["payload"])
            except Exception:
                pass
        out.append(d)
    return out


async def decide(
    action_id: uuid.UUID,
    *,
    decision: str,
    edit_note: Optional[str] = None,
) -> None:
    if decision not in {"approved", "rejected", "edited"}:
        raise ValueError(f"bad decision: {decision}")
    await db.execute(
        "update action_log set status = $1, edit_note = $2, decided_at = now() where id = $3",
        decision,
        edit_note,
        action_id,
    )


async def mark_executed(action_id: uuid.UUID, *, error: Optional[str] = None) -> None:
    await db.execute(
        "update action_log set status = $1, executed_at = now(), error = $2 where id = $3",
        "failed" if error else "executed",
        error,
        action_id,
    )
