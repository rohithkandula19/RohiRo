"""life report. a monthly rewind built from ro's own data.

build_report() gathers the month's numbers, each section best effort:
  • message volume per contact from the archive (vault rows excluded)
  • loops opened vs closed from commitments
  • actions approved / rejected / edited from the action log
  • token spend total plus the hungriest run labels
  • a messages-per-weekday histogram, the calendar-free busyness read

render_markdown() turns the numbers into an honest, warm "your month"
narrative in ro's voice. sections appear only when there is data behind
them. a quiet month gets a quiet fallback line instead of padding.

run() is the entrypoint: build, render, deliver through the digest
channels, and stash the result under the 'life_report_last' preference.
invoked by the scheduler monthly or by hand via __main__.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Iterable

from api.memory.db import db
from api.observability import budget
from api.observability.logging import log, setup_logging

REPORT_KEY = "life_report_last"

WEEKDAYS = (
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
)


# ----- pure parts -----


def weekday_histogram(pairs: Iterable[tuple[Any, Any]]) -> dict[str, int]:
    """fold (dow, count) pairs into an ordered weekday histogram.

    dow follows postgres extract(dow): 0 = sunday .. 6 = saturday.
    output keys run monday first. junk rows are skipped. returns {} when
    nothing counted, so callers can treat it as a missing section.
    """
    hist = {name: 0 for name in WEEKDAYS}
    for dow, count in pairs:
        try:
            dow_i = int(dow)
            count_i = int(count)
        except (TypeError, ValueError):
            continue
        if not 0 <= dow_i <= 6 or count_i <= 0:
            continue
        hist[WEEKDAYS[(dow_i - 1) % 7]] += count_i
    return hist if any(hist.values()) else {}


def render_markdown(report: dict[str, Any]) -> str:
    """the month, told straight. sections only where data exists."""
    report = report or {}
    days = int(report.get("days") or 30)
    body: list[str] = []

    messages = report.get("messages") or []
    if messages:
        total = sum(int(m.get("count") or 0) for m in messages)
        body.append("## people")
        body.append(
            f"{total} messages with your top {len(messages)} "
            f"{'person' if len(messages) == 1 else 'people'} "
            f"over the last {days} days."
        )
        for m in messages:
            body.append(f"- {m.get('contact')}: {int(m.get('count') or 0)}")

    loops = report.get("loops") or {}
    opened = int(loops.get("opened") or 0)
    closed = int(loops.get("closed") or 0)
    if opened or closed:
        body.append("## loops")
        if closed >= opened:
            body.append(
                f"you closed {closed} and opened {opened}. net ahead this month."
            )
        else:
            body.append(
                f"you opened {opened} and closed {closed}. a few still hanging."
            )

    actions = report.get("actions") or {}
    approved = int(actions.get("approved") or 0)
    rejected = int(actions.get("rejected") or 0)
    edited = int(actions.get("edited") or 0)
    if approved or rejected or edited:
        body.append("## actions")
        body.append(
            f"{approved} approved, {rejected} rejected, "
            f"{edited} edited before going out."
        )

    spend = report.get("spend") or {}
    if int(spend.get("tokens") or 0) > 0:
        body.append("## spend")
        body.append(
            f"{int(spend['tokens']):,} tokens across "
            f"{int(spend.get('calls') or 0)} calls."
        )
        for r in (spend.get("top_runs") or [])[:5]:
            body.append(f"- {r.get('run_label')}: {int(r.get('tokens') or 0):,}")

    weekdays = report.get("weekdays") or {}
    if weekdays:
        busiest = max(weekdays, key=lambda k: weekdays[k])
        body.append("## rhythm")
        body.append(f"{busiest} was your loudest day.")
        body.append(
            " · ".join(f"{name[:3]} {count}" for name, count in weekdays.items())
        )

    if not body:
        return "# your month\n\n(quiet month — not enough data yet)"
    return "\n".join(["# your month", ""] + body)


# ----- gathering (each section best effort) -----


async def build_report(days: int = 30) -> dict[str, Any]:
    """gather the month's numbers. a failed section is simply absent."""
    report: dict[str, Any] = {"days": days}

    try:
        rows = await db.fetch(
            """select contact_key as contact, count(*)::int as count
               from archive_messages
               where archived_at > now() - make_interval(days => $1)
                 and not vault and contact_key <> ''
               group by contact_key order by count desc limit 8""",
            days,
        )
        if rows:
            report["messages"] = [dict(r) for r in rows]
    except Exception as e:
        log.warning("life report messages section failed", error=str(e))

    try:
        opened = await db.fetchval(
            """select count(*) from commitments
               where created_at > now() - make_interval(days => $1)""",
            days,
        )
        closed = await db.fetchval(
            """select count(*) from commitments
               where resolved_at > now() - make_interval(days => $1)""",
            days,
        )
        report["loops"] = {"opened": int(opened or 0), "closed": int(closed or 0)}
    except Exception as e:
        log.warning("life report loops section failed", error=str(e))

    try:
        rows = await db.fetch(
            """select status, count(*)::int as count from action_log
               where created_at > now() - make_interval(days => $1)
                 and status in ('approved', 'rejected', 'edited')
               group by status""",
            days,
        )
        if rows:
            report["actions"] = {r["status"]: r["count"] for r in rows}
    except Exception as e:
        log.warning("life report actions section failed", error=str(e))

    try:
        total = await db.fetchrow(
            """select coalesce(sum(input_tokens + output_tokens), 0)::bigint as tokens,
                      count(*)::int as calls
               from spend_log
               where created_at > now() - make_interval(days => $1)""",
            days,
        )
        tops = await db.fetch(
            """select run_label, sum(input_tokens + output_tokens)::bigint as tokens
               from spend_log
               where created_at > now() - make_interval(days => $1)
               group by run_label order by tokens desc limit 5""",
            days,
        )
        report["spend"] = {
            "tokens": int(total["tokens"]),
            "calls": int(total["calls"]),
            "top_runs": [
                {"run_label": r["run_label"], "tokens": int(r["tokens"])} for r in tops
            ],
        }
    except Exception as e:
        log.warning("life report spend section failed", error=str(e))

    try:
        rows = await db.fetch(
            """select extract(dow from coalesce(sent_at, archived_at))::int as dow,
                      count(*)::int as count
               from archive_messages
               where archived_at > now() - make_interval(days => $1) and not vault
               group by 1""",
            days,
        )
        hist = weekday_histogram((r["dow"], r["count"]) for r in rows)
        if hist:
            report["weekdays"] = hist
    except Exception as e:
        log.warning("life report weekday section failed", error=str(e))

    return report


# ----- entrypoint -----


async def run() -> None:
    setup_logging()
    budget.set_run("life-report")
    log.info("life report starting")

    report = await build_report()
    markdown = render_markdown(report)

    try:
        from api.digest import deliver
        await deliver(markdown)
    except Exception as e:
        log.warning("life report delivery failed", error=str(e))

    try:
        await db.execute(
            """insert into preferences (key, value) values ($1, $2)
               on conflict (key) do update set value = excluded.value, updated_at = now()""",
            REPORT_KEY,
            json.dumps({
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "markdown": markdown,
                "report": report,
            }),
        )
    except Exception as e:
        log.warning("life report store failed", error=str(e))

    log.info("life report done", sections=sum(1 for k in report if k != "days"))


if __name__ == "__main__":
    asyncio.run(run())
