"""approval store. supervisor pauses, posts to action_log, resumes when ro decides."""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from api.memory.db import db
from api.observability.logging import log


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

    # ping the phone/browser. best-effort, never blocks the open.
    if requires_approval:
        try:
            import asyncio
            from api.integrations import webpush
            asyncio.get_running_loop().create_task(webpush.push_all(
                title="ro needs a yes",
                body=description[:200],
                url="/overview",
            ))
        except Exception:
            pass

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
) -> str:
    """decide a pending action. compare-and-swap: only a pending row can be
    decided, so concurrent decides cannot double-apply. returns one of
    "applied", "already_<status>", "not_found".
    """
    if decision not in {"approved", "rejected", "edited"}:
        raise ValueError(f"bad decision: {decision}")

    claimed = await db.fetchrow(
        """update action_log set status = $1, edit_note = $2, decided_at = now()
           where id = $3 and status = 'pending'
           returning tool, payload""",
        decision,
        edit_note,
        action_id,
    )

    if claimed is None:
        current = await db.fetchrow("select status from action_log where id = $1", action_id)
        if current is None:
            return "not_found"
        return f"already_{current['status']}"

    row = claimed

    # capture for the voice learner (best-effort; never block the decision)
    if row:
        payload = row["payload"]
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}
        try:
            from api.eval.voice_learner import capture_decision
            await capture_decision(
                action_id=action_id,
                tool=row["tool"],
                decision=decision,
                payload=payload or {},
                edit_note=edit_note,
            )
        except Exception:
            log.warning("voice signal capture failed", action_id=str(action_id))

    return "applied"


async def claim_for_execute(action_id: uuid.UUID) -> Optional[dict[str, Any]]:
    """atomically claim an approved or edited action for execution. only one
    caller can win the claim, so a send can never run twice. returns the row
    needed to execute, or None if the action is not claimable."""
    row = await db.fetchrow(
        """update action_log set status = 'executing'
           where id = $1 and status in ('approved', 'edited')
           returning id, tool, payload, edit_note""",
        action_id,
    )
    return dict(row) if row else None


async def mark_executed(
    action_id: uuid.UUID,
    *,
    error: Optional[str] = None,
    result: Optional[dict[str, Any]] = None,
) -> None:
    await db.execute(
        "update action_log set status = $1, executed_at = now(), error = $2, result = $3 where id = $4",
        "failed" if error else "executed",
        error,
        json.dumps(result) if result is not None else None,
        action_id,
    )
