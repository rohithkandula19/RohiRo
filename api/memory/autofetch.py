"""auto-fetch loop.

every ~15 min, ask each configured integration "anything new?" and write the
new things into the memory tree as raw_events. dedup via the seen_keys table.

each fetcher is its own function:
  fetch_gmail()       — unread or recent emails
  fetch_calendar()    — upcoming events in next 24h
  fetch_github()      — repos with new pushes
  fetch_slack()       — recent DMs with new activity
  fetch_imessage()    — recent texts with new activity

returns counts per source. cheap when nothing's new (just a small api call +
a few sql touches).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from api.integrations import gcal, github, gmail, imessage as imsg, slack as slack_int
from api.memory.db import db
from api.memory.tree import write_event
from api.observability.logging import log


async def _is_new(source: str, external_id: str) -> bool:
    """insert or detect dup. returns True iff this is a first-time sighting."""
    if not external_id:
        return False
    row = await db.fetchrow(
        """insert into seen_keys (source, external_id) values ($1, $2)
           on conflict (source, external_id) do nothing
           returning external_id""",
        source, external_id,
    )
    return row is not None


# ----- per-source fetchers -----


async def fetch_gmail() -> int:
    if not gmail.configured():
        return 0
    try:
        threads = await gmail.search_threads("newer_than:1d", max_results=20)
    except Exception as e:
        log.warning("autofetch gmail failed", error=str(e))
        return 0
    new = 0
    for t in threads:
        if not await _is_new("gmail", t.thread_id):
            continue
        new += 1
        who = t.from_name or t.from_email or "unknown"
        unread = " (unread)" if t.unread else ""
        await write_event(
            source="gmail",
            kind="email_observed",
            summary=f"email from {who}: {t.subject[:80]}{unread}",
            payload={"thread_id": t.thread_id, "from": t.from_email,
                     "subject": t.subject, "snippet": t.snippet[:300],
                     "unread": t.unread},
        )
    return new


async def fetch_calendar() -> int:
    if not gcal.configured():
        return 0
    now = datetime.now(tz=timezone.utc)
    try:
        events = await gcal.list_events(time_min=now, time_max=now + timedelta(days=2), max_results=25)
    except Exception as e:
        log.warning("autofetch calendar failed", error=str(e))
        return 0
    new = 0
    for e in events:
        if not await _is_new("calendar", e.event_id):
            continue
        new += 1
        await write_event(
            source="calendar",
            kind="event_upcoming",
            summary=f"meeting: {e.title} at {e.start}",
            payload={"event_id": e.event_id, "title": e.title, "start": e.start,
                     "end": e.end, "attendees": e.attendees},
            # don't change `when` — keep the autofetch timestamp distinct from event time
        )
    return new


async def fetch_github() -> int:
    if not github.configured():
        return 0
    try:
        repos = await github.list_my_repos(limit=20, sort="pushed")
    except Exception as e:
        log.warning("autofetch github failed", error=str(e))
        return 0
    new = 0
    for r in repos:
        key = f"{r.full_name}:{r.pushed_at}"
        if not await _is_new("github", key):
            continue
        new += 1
        await write_event(
            source="github",
            kind="repo_pushed",
            summary=f"{r.full_name} got new commits ({r.pushed_at})",
            payload={"repo": r.full_name, "pushed_at": r.pushed_at,
                     "language": r.language, "open_issues": r.open_issues},
        )
    return new


async def fetch_slack() -> int:
    if not slack_int.configured():
        return 0
    try:
        dms = await slack_int.list_recent_dms(limit=15)
    except Exception as e:
        log.warning("autofetch slack failed", error=str(e))
        return 0
    new = 0
    for d in dms:
        # we treat "this channel has any activity recently" as one event per scan;
        # dedup on channel_id keeps it from spamming. we re-emit if the dm appears
        # again with a different summary — but that's noise; skip.
        if not await _is_new("slack", d.channel_id):
            continue
        new += 1
        await write_event(
            source="slack",
            kind="dm_observed",
            summary=f"recent slack DM with {d.name}",
            payload={"channel_id": d.channel_id, "with": d.name},
        )
    return new


async def fetch_imessage() -> int:
    if not imsg.configured():
        return 0
    try:
        threads = await imsg.list_recent_threads(limit=15)
    except Exception as e:
        log.warning("autofetch imessage failed", error=str(e))
        return 0
    new = 0
    for t in threads:
        # dedup on chat_id + last message timestamp so updates re-emit
        key = f"{t.chat_id}:{t.last_at}"
        if not await _is_new("imessage", key):
            continue
        new += 1
        who = t.display_name
        snippet = ("you: " if t.last_from_me else "") + t.last_text[:160]
        await write_event(
            source="imessage",
            kind="thread_observed",
            summary=f"iMessage thread with {who}: {snippet}",
            payload={"chat_id": t.chat_id, "with": who,
                     "last_from_me": t.last_from_me, "last": t.last_text},
        )
    return new


# ----- orchestrator -----


async def run_once() -> dict[str, int]:
    """run every configured fetcher once, return per-source new-event counts."""
    results: dict[str, int] = {}
    for name, fn in [
        ("gmail", fetch_gmail),
        ("calendar", fetch_calendar),
        ("github", fetch_github),
        ("slack", fetch_slack),
        ("imessage", fetch_imessage),
    ]:
        try:
            results[name] = await fn()
        except Exception:
            log.exception("autofetch source failed", source=name)
            results[name] = 0
    return results
