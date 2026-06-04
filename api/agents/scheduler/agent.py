"""scheduler sub-agent.

handles "remind me…" / "every monday at 9am…" / "tomorrow at 5pm…" requests.
parses the user text into:

  kind   : 'cron' or 'once'
  spec   : 5-field cron expression OR iso timestamp
  text   : the request the supervisor will run when the schedule fires
  title  : human label

then opens an approval gate. on approval, the schedule row is inserted; the
background loop picks it up.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import dateparser
from croniter import croniter

from api.agents.base import Agent, AgentResult
from api.config import settings
from api.observability.logging import log
from api.scheduler import compute_next
from api.supervisor import approval

INTENT_PROMPT = """ro asked to schedule something. parse it into JSON.

shape (strict):
  {
    "kind": "cron" | "once" | "list" | "cancel" | "none",
    "spec": "<5-field cron expr>"  (for cron)
            | "<natural-language time>"  (for once — we'll parse below)
            | ""  (otherwise),
    "text": "<the instruction ro will run at fire time>",
    "title": "<short human label>",
    "timezone": "<iana timezone name or empty for local>"
  }

guidance:
- "every weekday at 9am, ..."        → cron, spec="0 9 * * 1-5"
- "every monday morning ..."         → cron, spec="0 9 * * 1"
- "every hour ..."                   → cron, spec="0 * * * *"
- "tomorrow at 5pm, ..."             → once, spec="tomorrow 5pm"
- "in 2 hours, ..."                  → once, spec="in 2 hours"
- "next monday, ..."                 → once, spec="next monday 9am"
- "list my schedules" / "what's scheduled" → kind="list"
- "cancel the morning brief" / "delete my reminder" → kind="cancel", title is the rough name

`text` should be the action verbatim (without the time part). e.g. for
"every monday 9am summarize the week" → text="summarize the week".

reply with only JSON. no fences, no preamble."""


class SchedulerAgent(Agent):
    async def run(self, *, session_id: str, user_text: str, context: dict[str, Any]) -> AgentResult:
        spec = await self._parse(user_text)
        kind = spec.get("kind", "none")
        if kind == "list":
            return await self._list()
        if kind == "cancel":
            return await self._cancel(spec)
        if kind in ("cron", "once"):
            return await self._propose(spec, user_text, session_id)
        return AgentResult(
            text="i can schedule recurring or one-off tasks. try things like:\n"
                 "  • \"every weekday at 9am, summarize my inbox and calendar\"\n"
                 "  • \"in 2 hours, remind me to take the laundry out\"\n"
                 "  • \"every monday morning, brief me on github\""
        )

    async def _propose(self, spec: dict[str, Any], user_text: str, session_id: str) -> AgentResult:
        kind = spec["kind"]
        raw_spec = (spec.get("spec") or "").strip()
        text = (spec.get("text") or "").strip() or user_text
        title = (spec.get("title") or "").strip() or text[:60]
        tz = (spec.get("timezone") or "").strip() or _local_tz()

        # validate / normalize the spec
        if kind == "cron":
            if not croniter.is_valid(raw_spec):
                return AgentResult(text=f"i couldn't parse `{raw_spec}` as a cron expression.")
            display_spec = raw_spec
        else:
            d = dateparser.parse(raw_spec, settings={"PREFER_DATES_FROM": "future"})
            if d is None:
                return AgentResult(text=f"i couldn't parse `{raw_spec}` as a time.")
            if d.tzinfo is None:
                from zoneinfo import ZoneInfo
                d = d.replace(tzinfo=ZoneInfo(tz))
            display_spec = d.isoformat()

        # compute the first fire time so the user sees it before approving
        try:
            next_at = compute_next(kind=kind, spec=display_spec, tz=tz)
        except Exception as e:
            return AgentResult(text=f"couldn't compute next fire time: {e}")

        action_id = await approval.open_approval(
            session_id=uuid.UUID(session_id),
            domain="scheduler",
            tool="schedule.create",
            description=f"{kind} schedule: {title[:80]}",
            payload={"kind": kind, "spec": display_spec, "text": text,
                     "title": title, "timezone": tz, "next_at": next_at.isoformat()},
            requires_approval=True,
        )

        nice_next = next_at.astimezone(_zone(tz)).strftime("%a %b %d  %-I:%M %p %Z")
        return AgentResult(
            text=f"i'll set this up if you approve.",
            actions_opened=[str(action_id)],
            tool_calls=[{
                "tool": "schedule.draft",
                "args": {},
                "result": {
                    "kind": kind, "spec": display_spec, "text": text,
                    "title": title, "timezone": tz,
                    "next_at": next_at.isoformat(),
                    "next_at_human": nice_next,
                },
            }],
        )

    async def _list(self) -> AgentResult:
        from api.scheduler import list_all
        items = await list_all()
        if not items:
            return AgentResult(text="no schedules set up.")
        lines = [f"{len(items)} schedule{'s' if len(items) != 1 else ''}:"]
        for s in items[:20]:
            tag = "" if s.enabled else " [off]"
            kind_label = "cron" if s.kind == "cron" else "once"
            lines.append(f"• [{kind_label}] {s.title}{tag} → next: {s.next_run_at[:16].replace('T',' ')}")
        return AgentResult(
            text="\n".join(lines),
            tool_calls=[{
                "tool": "schedule.list",
                "args": {},
                "result": [
                    {"id": s.id, "kind": s.kind, "spec": s.spec, "title": s.title,
                     "text": s.text, "enabled": s.enabled, "next_at": s.next_run_at,
                     "last_run_at": s.last_run_at}
                    for s in items
                ],
            }],
        )

    async def _cancel(self, spec: dict[str, Any]) -> AgentResult:
        from api.scheduler import list_all, delete
        target = (spec.get("title") or "").strip().lower()
        items = await list_all()
        # fuzzy match by title/text
        match = next(
            (s for s in items if target and (target in s.title.lower() or target in s.text.lower())),
            None,
        )
        if not match:
            return AgentResult(text=f"no schedule matching `{target}`. ask me 'list my schedules' first.")
        await delete(match.id)
        return AgentResult(text=f"cancelled `{match.title}`.")

    async def _parse(self, text: str) -> dict[str, Any]:
        try:
            raw = await self._ask(
                system=INTENT_PROMPT,
                messages=[{"role": "user", "content": text}],
                model=settings.model_cheap,
                max_tokens=300,
                temperature=0.0,
            )
            if raw.startswith("```"):
                raw = raw.strip("`")
                if raw.lower().startswith("json"):
                    raw = raw[4:]
            return json.loads(raw)
        except Exception:
            return {"kind": "none"}


def _local_tz() -> str:
    try:
        import tzlocal
        return str(tzlocal.get_localzone())
    except Exception:
        return "UTC"


def _zone(tz: str):
    from zoneinfo import ZoneInfo
    try:
        return ZoneInfo(tz)
    except Exception:
        return ZoneInfo("UTC")


scheduler_agent = SchedulerAgent(name="scheduler", system_prompt="")
