"""calendar sub-agent — google calendar wired.

intents the supervisor routes here:
- read_schedule  ("what's on my calendar today/tomorrow/this week")
- find_time      ("when can i meet sarah", "find 90 min on thursday")
- create_event   ("book a meeting with sarah tuesday 2pm for 1h")
- prep_brief     ("what's my next meeting", "brief me on the photon call")
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import dateparser

from api.agents.base import Agent, AgentResult
from api.config import settings
from api.integrations import gcal
from api.observability.logging import log
from api.supervisor import approval

INTENT_PROMPT = """classify the user's request about their calendar into one intent and extract params.

intents:
- "read_schedule": user wants to see their schedule (what's on, what do i have, today/tomorrow/this week)
- "find_time": user wants to find open slots (when can i meet, find time, when am i free, find 90 min)
- "create_event": user wants to schedule a new event (book, schedule, set up, add to calendar)
- "prep_brief": user wants a brief on an upcoming meeting (brief me, what's next, prep for X)
- "other": none of the above

params to extract:
- "when": natural-language time range or moment, if present (e.g. "today", "tomorrow", "this week", "thursday 2pm")
- "duration_min": integer if a duration is given (e.g. "90 min" → 90, "1 hour" → 60), else 0
- "with_whom": person name/email if mentioned, else ""
- "title": short event title if user is creating one, else ""

reply with json only, shape:
{"intent": "...", "when": "...", "duration_min": 0, "with_whom": "...", "title": "..."}"""


class CalendarAgent(Agent):
    async def run(self, *, session_id: str, user_text: str, context: dict[str, Any]) -> AgentResult:
        if not gcal.configured():
            return AgentResult(
                text=(
                    "i can't reach your calendar yet — your google account isn't connected.\n\n"
                    "one-time setup:\n"
                    "  1. create an oauth client at https://console.cloud.google.com/\n"
                    "  2. save the json to ~/.config/ro/google_client.json\n"
                    "  3. run `uv run python scripts/setup_google_oauth.py`\n\n"
                    "after that i can read your schedule, find free time, and book meetings."
                ),
                error="calendar_not_configured",
            )

        intent = await self._classify_intent(user_text)
        kind = intent.get("intent", "other")

        if kind == "read_schedule":
            return await self._read_schedule(intent)
        if kind == "find_time":
            return await self._find_time(intent)
        if kind == "create_event":
            return await self._create_event(intent, user_text, session_id)
        if kind == "prep_brief":
            return await self._prep_brief(intent, user_text)

        # default: show today
        return await self._read_schedule({"when": "today"})

    # ----- intents -----

    async def _read_schedule(self, intent: dict[str, Any]) -> AgentResult:
        when = intent.get("when") or "today"
        tmin, tmax, label = _parse_range(when)

        try:
            events = await gcal.list_events(time_min=tmin, time_max=tmax, max_results=30)
        except Exception as e:
            log.exception("gcal list failed")
            return AgentResult(text=f"couldn't read calendar. {e}", error=str(e))

        if not events:
            return AgentResult(text=f"nothing on {label}.")

        lines = [f"{len(events)} event{'s' if len(events) != 1 else ''} {label}:"]
        for e in events[:30]:
            t = _fmt_time(e.start, all_day=e.all_day)
            lines.append(f"• {t} — {e.title[:80]}")

        return AgentResult(
            text="\n".join(lines),
            tool_calls=[{
                "tool": "calendar.list",
                "args": {"when": when, "from": tmin.isoformat(), "to": tmax.isoformat()},
                "result": [asdict(e) for e in events],
            }],
        )

    async def _find_time(self, intent: dict[str, Any]) -> AgentResult:
        duration = intent.get("duration_min") or 30
        when = intent.get("when") or "this week"
        tmin, tmax, label = _parse_range(when)

        try:
            slots = await gcal.find_free(
                duration_min=duration,
                time_min=tmin,
                time_max=tmax,
                limit=6,
            )
        except Exception as e:
            return AgentResult(text=f"couldn't check freebusy. {e}", error=str(e))

        if not slots:
            return AgentResult(text=f"no open {duration}-min slots {label}.")

        lines = [f"{len(slots)} open slot{'s' if len(slots) != 1 else ''} ({duration} min) {label}:"]
        for s in slots:
            lines.append(f"• {_fmt_slot(s.start, s.end)}")

        return AgentResult(
            text="\n".join(lines),
            tool_calls=[{
                "tool": "calendar.find_free",
                "args": {"duration_min": duration, "when": when},
                "result": [asdict(s) for s in slots],
            }],
        )

    async def _create_event(
        self, intent: dict[str, Any], user_text: str, session_id: str,
    ) -> AgentResult:
        when = intent.get("when", "")
        duration = intent.get("duration_min") or 30
        with_whom = intent.get("with_whom", "")
        title = intent.get("title") or (f"meeting with {with_whom}" if with_whom else "meeting")

        start = dateparser.parse(when, settings={"PREFER_DATES_FROM": "future"}) if when else None
        if start is None:
            return AgentResult(
                text=f"i need a clearer time — '{when or '(missing)'}' didn't parse. "
                     "try `book a meeting with sarah tuesday 2pm for 1h`.",
            )
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc).astimezone()
        end = start + timedelta(minutes=duration)

        attendees = []
        if with_whom and "@" in with_whom:
            attendees = [with_whom]

        # open approval; execute() will actually call gcal.create_event
        action_id = await approval.open_approval(
            session_id=uuid.UUID(session_id),
            domain="calendar",
            tool="calendar.create_event",
            description=f"book '{title}' at {start.isoformat()}",
            payload={
                "title": title,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "attendees": attendees,
                "description": "",
                "location": "",
                "add_meet_link": bool(attendees),
            },
            requires_approval=True,
        )

        return AgentResult(
            text=f"i'll book this — confirm and i'll send it:",
            actions_opened=[str(action_id)],
            tool_calls=[{
                "tool": "calendar.draft_event",
                "args": {},
                "result": {
                    "title": title,
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "duration_min": duration,
                    "attendees": attendees,
                    "with_meet_link": bool(attendees),
                },
            }],
        )

    async def _prep_brief(self, intent: dict[str, Any], user_text: str) -> AgentResult:
        now = datetime.now(tz=timezone.utc)
        try:
            events = await gcal.list_events(time_min=now, time_max=now + timedelta(days=2), max_results=10)
        except Exception as e:
            return AgentResult(text=f"couldn't read calendar. {e}", error=str(e))

        if not events:
            return AgentResult(text="nothing on your calendar in the next two days.")

        target = events[0]
        # if user mentioned a specific person/topic, try to match
        topic = intent.get("with_whom", "")
        if topic:
            for e in events:
                if topic.lower() in (e.title.lower() + " " + " ".join(e.attendees).lower()):
                    target = e
                    break

        sys = (
            "you are ro's calendar agent writing a short, useful prep brief for an upcoming meeting. "
            "3-5 bullets max. concrete, not generic."
        )
        user = (
            f"meeting: {target.title}\n"
            f"when: {target.start}\n"
            f"with: {', '.join(target.attendees) or 'just ro'}\n"
            f"description: {target.description[:1500]}\n"
            f"location: {target.location or 'unknown'}\n\n"
            f"write a prep brief."
        )
        try:
            body = await self._ask(
                system=sys,
                messages=[{"role": "user", "content": user}],
                model=settings.model_default,
                max_tokens=400,
                temperature=0.5,
            )
        except Exception as e:
            body = f"(couldn't draft brief: {e})"

        return AgentResult(
            text=f"# {target.title}\n_{_fmt_time(target.start, all_day=target.all_day)}_\n\n{body}",
            tool_calls=[{
                "tool": "calendar.prep_brief",
                "args": {"event_id": target.event_id},
                "result": asdict(target),
            }],
        )

    async def _classify_intent(self, text: str) -> dict[str, Any]:
        try:
            raw = await self._ask(
                system=INTENT_PROMPT,
                messages=[{"role": "user", "content": text}],
                model=settings.model_cheap,
                max_tokens=160,
                temperature=0.0,
            )
            if raw.startswith("```"):
                raw = raw.strip("`")
                if raw.lower().startswith("json"):
                    raw = raw[4:]
            return json.loads(raw)
        except Exception:
            return {"intent": "other", "when": "", "duration_min": 0, "with_whom": "", "title": ""}


# ----- range / time helpers -----


def _parse_range(when: str) -> tuple[datetime, datetime, str]:
    """natural language → (start, end, human label). always returns tz-aware utc."""
    now = datetime.now(tz=timezone.utc).astimezone()
    s = (when or "").strip().lower()

    if s in ("", "today"):
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1), "today"
    if s == "tomorrow":
        start = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1), "tomorrow"
    if "week" in s:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=7), "this week"
    if "month" in s:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=30), "this month"

    # try dateparser
    d = dateparser.parse(when, settings={"PREFER_DATES_FROM": "future"})
    if d:
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc).astimezone()
        start = d.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1), d.strftime("%a %b %d")

    # fallback: next 7 days
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=7), "the next 7 days"


def _fmt_time(iso: str, *, all_day: bool = False) -> str:
    if not iso:
        return ""
    try:
        if all_day:
            d = datetime.fromisoformat(iso)
            return d.strftime("%a %b %d (all day)")
        d = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
        return d.strftime("%a %b %d  %-I:%M %p")
    except Exception:
        return iso


def _fmt_slot(start_iso: str, end_iso: str) -> str:
    try:
        s = datetime.fromisoformat(start_iso.replace("Z", "+00:00")).astimezone()
        e = datetime.fromisoformat(end_iso.replace("Z", "+00:00")).astimezone()
        return f"{s.strftime('%a %b %d  %-I:%M %p')} – {e.strftime('%-I:%M %p')}"
    except Exception:
        return f"{start_iso} – {end_iso}"


calendar_agent = CalendarAgent(name="calendar", system_prompt="")
