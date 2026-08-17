"""classify intent into one or more domains.

uses haiku (the cheap model) for speed. returns a small json structure
the supervisor uses to dispatch.
"""

from __future__ import annotations

import json
from typing import Any

from api.config import settings
from api.observability.claude import claude_client
from api.observability.logging import log

DOMAINS = [
    "comms", "calendar", "code", "jobs", "research", "files",
    "finance", "health", "admin", "content", "memory",
    "notion",     # pages, search, create, append
    "linear",     # issues, search, create, comment
    "digest",     # morning brief / daily summary
    "actions",    # shell.run, file.write, web.fetch
    "scheduler",  # cron + once reminders
    "chat",
]

CLASSIFY_PROMPT = """you classify ro's request into one or more domains.

domains:
- comms: email, slack, imessage, telegram, whatsapp, linkedin
- calendar: meetings, scheduling, prep
- code: github, repos, commits, prs, deploys
- jobs: applications, recruiters, interviews
- research: papers, arxiv, web search
- files: drive, local files, notion
- finance: balances, expenses, subscriptions
- health: workouts, sleep, steps
- admin: bills, reminders, travel
- content: resume, blog, portfolio drafts
- memory: profile, contacts, decisions, history
- notion: notion pages, databases, "search notion", "new notion page", "append to my X page"
- scheduler: anything that schedules a future action — "every monday at 9am", "remind me in 2 hours", "tomorrow at 5pm", "list my schedules", "cancel my reminder"
- linear: linear (linear.app) issues — "my linear issues", "show RO-42", "new issue in RO: X", "comment on RO-42: ..."
- digest: a roll-up of everything — "brief me", "morning brief", "daily digest", "what's my day look like", "catch me up"
- actions: arbitrary shell commands, file writes to ro's scratch dir, http requests. use when the request doesn't match any other vertical but ro is being asked to do something concrete on the machine or the web (run X, fetch URL, save a note, append to a file).
- chat: just a question, no action

reply with json only. shape:
{"domains": ["..."], "intent": "one short sentence", "needs_action": true/false}

needs_action is true if ro is asking you to do something (draft, send, schedule, query a tool, run a command, save a file). false if just chatting.
"""


async def classify(text: str) -> dict[str, Any]:
    if not text.strip():
        return {"domains": ["chat"], "intent": "", "needs_action": False}

    def _parse(raw: str) -> dict[str, Any] | None:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:]
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None

    try:
        # local tier first: free, private, sub-second when ollama is up.
        # any miss (unset, down, bad json) falls through to claude.
        result = None
        try:
            from api.observability import llm_local
            local = await llm_local.chat(system=CLASSIFY_PROMPT, user=text, max_tokens=200)
            if local:
                result = _parse(local)
        except Exception:
            result = None

        if result is None:
            resp = await claude_client.message(
                model=settings.model_cheap,
                system=CLASSIFY_PROMPT,
                messages=[{"role": "user", "content": text}],
                max_tokens=200,
                temperature=0.0,
            )
            body = "".join(b.text for b in resp.content if b.type == "text").strip()
            result = _parse(body)
        if result is None:
            raise ValueError("classifier returned unparseable output")
        domains = result.get("domains") or ["chat"]
        domains = [d for d in domains if d in DOMAINS] or ["chat"]
        return {
            "domains": domains,
            "intent": (result.get("intent") or "").strip(),
            "needs_action": bool(result.get("needs_action", False)),
        }
    except Exception as e:
        log.warning("classify failed, defaulting to chat", error=str(e))
        return {"domains": ["chat"], "intent": text[:140], "needs_action": False}
