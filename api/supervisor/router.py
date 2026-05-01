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
    "chat",  # default, no domain action needed
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
- chat: just a question, no action

reply with json only. shape:
{"domains": ["..."], "intent": "one short sentence", "needs_action": true/false}

needs_action is true if ro is asking you to do something (draft, send, schedule, query a tool). false if just chatting.
"""


async def classify(text: str) -> dict[str, Any]:
    if not text.strip():
        return {"domains": ["chat"], "intent": "", "needs_action": False}

    try:
        resp = await claude_client.message(
            model=settings.model_cheap,
            system=CLASSIFY_PROMPT,
            messages=[{"role": "user", "content": text}],
            max_tokens=200,
            temperature=0.0,
        )
        body = "".join(b.text for b in resp.content if b.type == "text").strip()
        # tolerate fences.
        if body.startswith("```"):
            body = body.strip("`")
            if body.lower().startswith("json"):
                body = body[4:]
        result = json.loads(body)
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
