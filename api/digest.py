"""daily digest — the morning brief.

build_digest() assembles a single brief from everything ro knows:
  • today's calendar
  • recent unread/important email
  • open PRs + repo activity
  • yesterday's memory-tree summary
  • pending approvals waiting on you
  • the people/projects ro saw most recently

each section is guarded — unconfigured integrations are silently skipped, so
the digest works no matter how much you've connected. claude weaves the raw
sections into a tight brief in ro's voice (falls back to the structured
sections if claude is unavailable).

invoked two ways:
  • the scheduler ("every weekday at 8am, morning brief")
  • the supervisor routes "brief me" / "daily digest" here
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from api.config import settings
from api.memory.db import db
from api.observability.claude import claude_client
from api.observability.logging import log, setup_logging


async def build_digest() -> dict[str, Any]:
    """assemble the morning brief. returns {markdown, sections}."""
    sections: dict[str, Any] = {}

    sections["calendar"] = await _calendar_section()
    sections["email"] = await _email_section()
    sections["code"] = await _code_section()
    sections["yesterday"] = await _yesterday_section()
    sections["pending"] = await _pending_section()
    sections["people"] = await _people_section()

    markdown = await _weave(sections)
    return {"markdown": markdown, "sections": sections}


# ----- sections (each guarded; returns a small dict or None) -----


async def _calendar_section() -> dict[str, Any] | None:
    try:
        from api.integrations import gcal
        if not gcal.configured():
            return None
        now = datetime.now(tz=timezone.utc)
        end = now.replace(hour=23, minute=59, second=59)
        events = await gcal.list_events(time_min=now, time_max=end, max_results=12)
        return {"events": [
            {"title": e.title, "start": e.start, "attendees": e.attendees[:4]}
            for e in events
        ]}
    except Exception as e:
        log.warning("digest calendar section failed", error=str(e))
        return None


async def _email_section() -> dict[str, Any] | None:
    try:
        from api.integrations import gmail
        if not gmail.configured():
            return None
        threads = await gmail.search_threads("is:unread newer_than:2d", max_results=8)
        return {"unread": [
            {"from": t.from_name or t.from_email, "subject": t.subject}
            for t in threads
        ]}
    except Exception as e:
        log.warning("digest email section failed", error=str(e))
        return None


async def _code_section() -> dict[str, Any] | None:
    try:
        from api.integrations import github
        if not github.configured():
            return None
        prs = await github.list_open_prs()
        return {"open_prs": [
            {"repo": p.repo, "number": p.number, "title": p.title} for p in prs[:8]
        ]}
    except Exception as e:
        log.warning("digest code section failed", error=str(e))
        return None


async def _yesterday_section() -> dict[str, Any] | None:
    try:
        from api.memory.tree import engine as tree
        node = await tree.get_brief(period="yesterday")
        if not node or not node.summary_md.strip():
            return None
        return {"summary": node.summary_md[:1200]}
    except Exception as e:
        log.warning("digest yesterday section failed", error=str(e))
        return None


async def _pending_section() -> dict[str, Any] | None:
    rows = await db.fetch(
        "select tool, description from action_log where status = 'pending' order by created_at desc limit 8"
    )
    if not rows:
        return None
    return {"pending": [{"tool": r["tool"], "description": r["description"]} for r in rows]}


async def _people_section() -> dict[str, Any] | None:
    rows = await db.fetch(
        """select name, kind, seen_count from entities
           where last_seen_at >= now() - interval '3 days'
           order by seen_count desc, last_seen_at desc limit 6"""
    )
    if not rows:
        return None
    return {"recent": [{"name": r["name"], "kind": r["kind"]} for r in rows]}


# ----- weave -----


def _structured_fallback(sections: dict[str, Any]) -> str:
    lines = ["# morning brief", ""]
    cal = sections.get("calendar")
    if cal and cal["events"]:
        lines.append("## today")
        for e in cal["events"]:
            t = (e["start"] or "")[11:16]
            lines.append(f"- {t} {e['title']}")
        lines.append("")
    em = sections.get("email")
    if em and em["unread"]:
        lines.append(f"## unread email ({len(em['unread'])})")
        for u in em["unread"][:5]:
            lines.append(f"- {u['from']}: {u['subject']}")
        lines.append("")
    code = sections.get("code")
    if code and code["open_prs"]:
        lines.append("## open PRs")
        for p in code["open_prs"][:5]:
            lines.append(f"- {p['repo']}#{p['number']} {p['title']}")
        lines.append("")
    pend = sections.get("pending")
    if pend and pend["pending"]:
        lines.append("## waiting on you")
        for p in pend["pending"]:
            lines.append(f"- {p['description']}")
        lines.append("")
    ppl = sections.get("people")
    if ppl and ppl["recent"]:
        names = ", ".join(p["name"] for p in ppl["recent"])
        lines.append("## recently active")
        lines.append(names)
        lines.append("")
    y = sections.get("yesterday")
    if y:
        lines.append("## yesterday")
        lines.append(y["summary"])
    return "\n".join(lines).strip() or "nothing to brief — quiet morning."


async def _weave(sections: dict[str, Any]) -> str:
    # if there's literally nothing, short-circuit
    if not any(sections.values()):
        return "quiet morning — nothing on the calendar, no unread mail, no pending approvals."

    import json
    sys = (
        "you are ro writing rohith's morning brief. take the raw sections and "
        "write a tight, scannable brief. lead with what needs attention today "
        "(meetings, pending approvals), then unread email, then code, then a "
        "one-line recap of yesterday. use short markdown. no preamble, no "
        "'good morning' fluff beyond one short opener. skip empty sections."
    )
    user = "raw sections (json):\n\n" + json.dumps(
        {k: v for k, v in sections.items() if v}, indent=2, default=str
    )
    try:
        resp = await claude_client.message(
            model=settings.model_default,
            system=sys,
            messages=[{"role": "user", "content": user}],
            max_tokens=900,
            temperature=0.4,
            fallback_model=settings.model_cheap,
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        return text or _structured_fallback(sections)
    except Exception as e:
        log.warning("digest weave failed, using structured fallback", error=str(e))
        return _structured_fallback(sections)


# ----- delivery (proactive: ro messages you first) -----


async def deliver(markdown: str) -> dict[str, bool]:
    """send the digest through every configured channel. best effort each."""
    delivered: dict[str, bool] = {}
    text = markdown.strip()
    if not text:
        return delivered

    # imessage ro channel
    try:
        from api.config import secrets
        from api.integrations import imessage as imsg
        from api.listeners import gateway
        channel = (secrets.get("imessage_channel") or "").strip()
        if channel and imsg.configured():
            await gateway.record_sent("imessage", channel, text)
            from api.observability import ledger
            await ledger.record(basis="digest", channel="imessage", destination=channel, payload=text)
            delivered["imessage"] = await imsg.send_message(channel, text)
    except Exception:
        log.warning("digest imessage delivery failed")
        delivered["imessage"] = False

    # telegram owner dm
    try:
        from api.integrations import telegram as tg
        owner = tg.owner_id()
        if tg.configured() and owner is not None:
            await tg.send_message(int(owner), text[:4000])
            delivered["telegram"] = True
    except Exception:
        log.warning("digest telegram delivery failed")
        delivered["telegram"] = False

    # web push (headline only)
    try:
        from api.integrations import webpush
        first_line = next((ln.strip("# ").strip() for ln in text.splitlines() if ln.strip()), "digest ready")
        res = await webpush.push_all(title="ro · morning digest", body=first_line[:200], url="/overview")
        delivered["push"] = bool(res.get("sent"))
    except Exception:
        delivered["push"] = False

    return delivered


# ----- cli entry (launchd) -----


async def run() -> None:
    setup_logging()
    from api.observability import budget
    budget.set_run("routine:digest")
    result = await build_digest()
    print(result["markdown"])
    outcomes = await deliver(result["markdown"])
    if outcomes:
        log.info("digest delivered", **{k: str(v) for k, v in outcomes.items()})


if __name__ == "__main__":
    asyncio.run(run())
