"""chat slash-commands. instant answers, no model call, no spend.

any channel: message starting with "/" is a control command handled here
before triggers and the supervisor. unknown commands fall through to the
model, so "/shrug whatever" still gets a conversational answer.

/status   workers, spend, pending approvals, pause state
/loops    open commitments with age
/spend    today's tokens by run
/sent     today's egress receipts
/pause 2  pause background runs for n hours (default 4)
/resume   resume background runs
/help     this list
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from api.memory.db import db

PAUSE_KEY = "paused_until"
HELP = (
    "commands: /status /loops /spend /sent /pause [hours] /resume /help. "
    "anything else goes to the model."
)


async def paused_until() -> Optional[datetime]:
    row = await db.fetchrow("select value from preferences where key = $1", PAUSE_KEY)
    if not row:
        return None
    value = row["value"]
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            return None
    try:
        ts = datetime.fromisoformat(str(value))
        return ts if ts > datetime.now(tz=timezone.utc) else None
    except Exception:
        return None


async def is_paused() -> bool:
    return await paused_until() is not None


async def handle(text: str) -> Optional[str]:
    """returns a reply for a recognized command, None to fall through."""
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None
    parts = stripped.split()
    cmd = parts[0].lower()

    if cmd == "/help":
        return HELP

    if cmd == "/status":
        beats = await db.fetch(
            "select name, ok, beat_at from heartbeats order by name"
        )
        worker_lines = [
            f"{'🟢' if b['ok'] and b['beat_at'] and (datetime.now(tz=timezone.utc) - b['beat_at']).total_seconds() < 300 else '🔴'} {b['name'].replace('_', ' ')}"
            for b in beats
        ] or ["(no workers beating yet)"]
        spend = await db.fetchrow(
            "select coalesce(sum(input_tokens+output_tokens),0) as t, count(*) as c from spend_log where created_at >= date_trunc('day', now())"
        )
        pending = await db.fetchrow(
            "select count(*) as n from action_log where status = 'pending'"
        )
        pause = await paused_until()
        pause_line = f"⏸ paused until {pause.strftime('%H:%M')}" if pause else "▶ running"
        return (
            f"{pause_line}\n"
            + "\n".join(worker_lines)
            + f"\ntoday: {spend['t']:,} tokens / {spend['c']} calls"
            + f"\npending approvals: {pending['n']}"
        )

    if cmd == "/loops":
        from api.memory.commitments import open_loops
        loops = await open_loops(limit=10)
        if not loops:
            return "no open loops."
        return "\n".join(
            f"[{l['direction']}] {l['who'] + ': ' if l['who'] else ''}{l['what']}"
            f"{' — ' + l['due_hint'] if l['due_hint'] else ''} ({l['age_days']}d)"
            for l in loops
        )

    if cmd == "/spend":
        rows = await db.fetch(
            """select run_label, sum(input_tokens+output_tokens) as t, count(*) as c
               from spend_log where created_at >= date_trunc('day', now())
               group by run_label order by t desc limit 10"""
        )
        if not rows:
            return "no spend today."
        return "\n".join(f"{r['run_label']}: {r['t']:,} tokens ({r['c']} calls)" for r in rows)

    if cmd == "/sent":
        rows = await db.fetch(
            """select basis, channel, destination, created_at from egress_ledger
               where created_at >= date_trunc('day', now())
               order by id desc limit 15"""
        )
        if not rows:
            return "nothing sent today. the ledger is empty and verifiable."
        return "\n".join(
            f"{r['created_at'].strftime('%H:%M')} [{r['basis']}] {r['channel']} → {r['destination'] or '(you)'}"
            for r in rows
        )

    if cmd == "/pause":
        hours = 4
        if len(parts) > 1:
            try:
                hours = max(1, min(48, int(parts[1])))
            except ValueError:
                pass
        from datetime import timedelta
        until = datetime.now(tz=timezone.utc) + timedelta(hours=hours)
        await db.execute(
            """insert into preferences (key, value) values ($1, $2)
               on conflict (key) do update set value = excluded.value, updated_at = now()""",
            PAUSE_KEY, json.dumps(until.isoformat()),
        )
        return f"paused background runs (routines, triggers, bots) for {hours}h. chat still works. /resume to undo."

    if cmd == "/resume":
        await db.execute("delete from preferences where key = $1", PAUSE_KEY)
        return "resumed. background runs are live again."

    return None  # unknown slash command: let the model have it
