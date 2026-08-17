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
from api.observability import budget
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


MAX_CONSECUTIVE_FAILURES = 3


async def fire(s: Schedule) -> dict[str, Any]:
    """run a schedule with a claim-before-fire.

    the claim advances next_run_at (cron) or disables the row (once) BEFORE the
    run, via compare-and-swap on next_run_at <= now(). a crash mid-run skips
    that occurrence instead of re-firing it on restart, and two loops can never
    fire the same occurrence twice. a broken cron spec disables the schedule
    instead of refiring every tick. the budget guard vetoes runs (and re-fires)
    once the daily token budget is spent.
    """
    allowed, why = await budget.allow_run("routine")
    if not allowed:
        log.warning("scheduler run vetoed by budget", schedule=s.id, why=why)
        return {"id": s.id, "result": f"skipped: {why}"}
    if s.kind == "once":
        claimed = await db.fetchrow(
            """update schedules set enabled=false, last_run_at=now(), updated_at=now()
               where id=$1 and enabled and next_run_at <= now() returning id""",
            uuid.UUID(s.id),
        )
    else:
        try:
            next_at = compute_next(kind=s.kind, spec=s.spec, tz=s.timezone)
        except Exception as e:
            log.exception("scheduler compute_next failed, disabling", schedule=s.id)
            await db.execute(
                "update schedules set enabled=false, last_result=$2, updated_at=now() where id=$1",
                uuid.UUID(s.id), f"(disabled: bad spec: {e})"[:8000],
            )
            _notify(title="ro · schedule disabled", message=f"{s.title[:80]}: bad spec")
            return {"id": s.id, "result": "disabled: bad spec"}
        claimed = await db.fetchrow(
            """update schedules set last_run_at=now(), next_run_at=$2, updated_at=now()
               where id=$1 and enabled and next_run_at <= now() returning id""",
            uuid.UUID(s.id), next_at,
        )

    if claimed is None:
        # another loop claimed this occurrence, or it was disabled meanwhile.
        return {"id": s.id, "result": "skipped: already claimed"}

    sid = uuid.uuid4()
    failed = False
    budget.set_run(f"routine:{s.title or s.id}")
    try:
        if s.text.strip().lower().startswith("playbook:"):
            from api import playbooks as pb
            name = s.text.split(":", 1)[1].strip()
            outcome = await pb.run_playbook(name)
            done = outcome.get("completed", 0)
            total = outcome.get("total", 0)
            last = (outcome.get("steps") or [{}])[-1]
            text = f"playbook {name}: {done}/{total} steps. {last.get('text') or last.get('error') or ''}".strip()
            failed = not outcome.get("ran") or done < total
        elif s.text.strip().lower().startswith("bot:"):
            from api import crew
            rest = s.text.split(":", 1)[1].strip()
            bot_name, _, bot_task = rest.partition(":")
            outcome = await crew.run_bot(bot_name.strip(), bot_task.strip() or "run your standing charter duties.")
            text = f"bot {bot_name.strip()}: {(outcome.get('text') or outcome.get('error') or outcome.get('reason') or '')[:4000]}"
            failed = not outcome.get("ran") or bool(outcome.get("error"))
        else:
            result = await run_supervisor(session_id=sid, user_text=s.text)
            text = (result.get("text") or "").strip()
    except Exception as e:
        log.exception("scheduler fire failed", schedule=s.id)
        text = f"(failed: {e})"
        failed = True

    if failed:
        row = await db.fetchrow(
            """update schedules set last_result=$2, consecutive_failures = consecutive_failures + 1, updated_at=now()
               where id=$1 returning consecutive_failures""",
            uuid.UUID(s.id), text[:8000],
        )
        if row and row["consecutive_failures"] >= MAX_CONSECUTIVE_FAILURES:
            await db.execute(
                "update schedules set enabled=false, updated_at=now() where id=$1",
                uuid.UUID(s.id),
            )
            _notify(title="ro · schedule disabled",
                    message=f"{s.title[:80]}: {row['consecutive_failures']} failures in a row")
    else:
        await db.execute(
            "update schedules set last_result=$2, consecutive_failures=0, updated_at=now() where id=$1",
            uuid.UUID(s.id), text[:8000],
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


_NOTIFY_SCRIPT = '''
on run argv
    display notification (item 2 of argv) with title (item 1 of argv)
end run
'''


def _notify(*, title: str, message: str) -> None:
    """macos native notification via osascript. argv-passed, silent failure."""
    try:
        subprocess.run(
            ["osascript", "-e", _NOTIFY_SCRIPT, title[:120], message.replace("\n", " ")[:240]],
            timeout=5, capture_output=True, check=False,
        )
    except Exception:
        pass
