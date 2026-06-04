"""scheduler engine.

verbs (called by the route + the background loop):

- create(kind, spec, text, title, tz)         -> id
- list_all()
- delete(id)
- compute_next(spec, kind, tz, from_)         -> datetime
- due_now()                                   -> list[Schedule]
- fire(schedule)                              -> supervisor result; updates next_run_at

a "cron" spec is a 5-field unix cron expression; the cron is interpreted in
the schedule's `timezone`. a "once" spec is an iso timestamp (with offset);
once it fires, the schedule is disabled.
"""

from __future__ import annotations

import asyncio
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from croniter import croniter
from zoneinfo import ZoneInfo

from api.memory.db import db
from api.memory.tree import write_event as tree_write
from api.observability.logging import log
from api.supervisor import run_supervisor


@dataclass
class Schedule:
    id: str
    kind: str           # cron | once
    spec: str
    text: str
    timezone: str
    title: str
    enabled: bool
    last_run_at: str | None
    next_run_at: str
    last_result: str | None
    created_at: str


# ----- core helpers -----


def compute_next(*, kind: str, spec: str, tz: str, from_: Optional[datetime] = None) -> datetime:
    """when should this schedule next fire? always returns tz-aware utc."""
    now = (from_ or datetime.now(tz=timezone.utc)).astimezone(timezone.utc)
    if kind == "once":
        # spec is an iso timestamp; assume utc if no tz
        try:
            d = datetime.fromisoformat(spec)
        except Exception as e:
            raise ValueError(f"bad once spec '{spec}': {e}")
        if d.tzinfo is None:
            d = d.replace(tzinfo=ZoneInfo(tz))
        return d.astimezone(timezone.utc)

    if kind == "cron":
        try:
            zone = ZoneInfo(tz)
        except Exception:
            zone = ZoneInfo("UTC")
        local_now = now.astimezone(zone)
        c = croniter(spec, local_now)
        nxt = c.get_next(datetime)
        if nxt.tzinfo is None:
            nxt = nxt.replace(tzinfo=zone)
        return nxt.astimezone(timezone.utc)

    raise ValueError(f"unknown schedule kind: {kind}")


# ----- crud -----


async def create(*, kind: str, spec: str, text: str, title: str = "", tz: str = "UTC") -> str:
    next_at = compute_next(kind=kind, spec=spec, tz=tz)
    row = await db.fetchrow(
        """insert into schedules (kind, spec, text, title, timezone, next_run_at)
           values ($1, $2, $3, $4, $5, $6) returning id::text""",
        kind, spec, text, title or text[:80], tz, next_at,
    )
    return row["id"]


async def list_all() -> list[Schedule]:
    rows = await db.fetch(
        """select id::text, kind, spec, text, title, timezone, enabled,
                  last_run_at, next_run_at, last_result, created_at
           from schedules order by enabled desc, next_run_at asc"""
    )
    out: list[Schedule] = []
    for r in rows:
        out.append(Schedule(
            id=r["id"], kind=r["kind"], spec=r["spec"], text=r["text"],
            title=r["title"], timezone=r["timezone"], enabled=r["enabled"],
            last_run_at=r["last_run_at"].isoformat() if r["last_run_at"] else None,
            next_run_at=r["next_run_at"].isoformat(),
            last_result=r["last_result"],
            created_at=r["created_at"].isoformat(),
        ))
    return out


async def delete(schedule_id: str) -> bool:
    row = await db.fetchrow("delete from schedules where id = $1 returning id::text", uuid.UUID(schedule_id))
    return row is not None


async def disable(schedule_id: str) -> None:
    await db.execute("update schedules set enabled = false, updated_at = now() where id = $1", uuid.UUID(schedule_id))


async def due_now() -> list[Schedule]:
    rows = await db.fetch(
        """select id::text, kind, spec, text, title, timezone, enabled,
                  last_run_at, next_run_at, last_result, created_at
           from schedules
           where enabled and next_run_at <= now()
           order by next_run_at asc
           limit 20"""
    )
    return [
        Schedule(
            id=r["id"], kind=r["kind"], spec=r["spec"], text=r["text"],
            title=r["title"], timezone=r["timezone"], enabled=r["enabled"],
            last_run_at=r["last_run_at"].isoformat() if r["last_run_at"] else None,
            next_run_at=r["next_run_at"].isoformat(),
            last_result=r["last_result"],
            created_at=r["created_at"].isoformat(),
        ) for r in rows
    ]


# ----- fire -----


async def fire(s: Schedule) -> dict[str, Any]:
    """run a schedule. updates last_run_at, computes next_run_at, notifies."""
    sid = uuid.uuid4()
    try:
        result = await run_supervisor(session_id=sid, user_text=s.text)
        text = (result.get("text") or "").strip()
    except Exception as e:
        log.exception("scheduler fire failed", schedule=s.id)
        text = f"(failed: {e})"

    # update schedule
    if s.kind == "once":
        await db.execute(
            "update schedules set enabled=false, last_run_at=now(), last_result=$2, updated_at=now() where id=$1",
            uuid.UUID(s.id), text[:8000],
        )
    else:
        try:
            next_at = compute_next(kind=s.kind, spec=s.spec, tz=s.timezone)
        except Exception:
            next_at = datetime.now(tz=timezone.utc)
        await db.execute(
            "update schedules set last_run_at=now(), next_run_at=$2, last_result=$3, updated_at=now() where id=$1",
            uuid.UUID(s.id), next_at, text[:8000],
        )

    # log + notify
    try:
        await tree_write(
            source="scheduler",
            kind=f"schedule_fired",
            summary=f"scheduled: {s.title[:80]} — {text[:160]}",
            payload={"schedule_id": s.id, "text": s.text, "result_excerpt": text[:600]},
        )
    except Exception:
        log.warning("scheduler tree write failed", schedule=s.id)

    _notify(title=f"ro · {s.title[:50]}", message=text[:240] or "(no reply)")
    return {"id": s.id, "result": text}


def _notify(*, title: str, message: str) -> None:
    """macos native notification via osascript. silent failure."""
    try:
        safe_title = title.replace('"', "'")
        safe_msg = message.replace('"', "'").replace("\n", " ")
        subprocess.run(
            ["osascript", "-e", f'display notification "{safe_msg}" with title "{safe_title}"'],
            timeout=5, capture_output=True, check=False,
        )
    except Exception:
        pass
