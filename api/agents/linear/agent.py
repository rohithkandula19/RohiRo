"""linear sub-agent.

intents:
- list_mine    "show my linear issues" / "what am i working on"
- search       "find issues about photon"
- read         "show me RO-42"
- create       "new issue in RO: ship slack integration"        [approval]
- comment      "comment on RO-42: blocked on review"            [approval]
- projects     "list my linear projects"
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict
from typing import Any

from api.agents.base import Agent, AgentResult
from api.config import settings
from api.integrations import linear
from api.observability.logging import log
from api.supervisor import approval

INTENT_PROMPT = """classify a request about linear and extract params.

intents:
- "list_mine":  show my issues (assigned to me, active by default)
- "search":     find issues by topic or text
- "read":       show one issue (identifier like "RO-42" given)
- "create":     create a new issue (mentions create/new/file)
- "comment":    comment on an issue (mentions identifier + commentary)
- "projects":   list projects
- "other":      none of the above

params (extract what's present):
- "query":       search terms for "search"
- "identifier":  e.g. "RO-42" for read/comment
- "team_key":    short team prefix e.g. "RO" for create
- "title":       a clear issue title for create
- "description": longer body for create
- "comment_body": text to post as a comment
- "status":      "active" | "all" | "completed"  (default active for list_mine)

reply with ONLY a JSON object:
{"intent":"...", "query":"...", "identifier":"...", "team_key":"...",
 "title":"...", "description":"...", "comment_body":"...", "status":"..."}"""

IDENT_RE = re.compile(r"\b([A-Z][A-Z0-9_]{0,9})-(\d{1,6})\b")


class LinearAgent(Agent):
    async def run(self, *, session_id: str, user_text: str, context: dict[str, Any]) -> AgentResult:
        if not linear.configured():
            return AgentResult(
                text=(
                    "i can't reach linear yet.\n\n"
                    "one-time setup:\n"
                    "  1. linear.app → settings → account → security & access → personal API keys\n"
                    "  2. create one, copy it\n"
                    "  3. `keyring set ro linear_token`"
                ),
                error="linear_not_configured",
            )

        spec = await self._classify(user_text)
        kind = spec.get("intent", "other")

        # auto-pull identifier from user_text if not in spec
        if not spec.get("identifier"):
            m = IDENT_RE.search(user_text)
            if m:
                spec["identifier"] = f"{m.group(1)}-{m.group(2)}"

        if kind == "list_mine":
            return await self._list_mine(spec)
        if kind == "search":
            return await self._search(spec, user_text)
        if kind == "read":
            return await self._read(spec)
        if kind == "create":
            return await self._create(spec, user_text, session_id)
        if kind == "comment":
            return await self._comment(spec, user_text, session_id)
        if kind == "projects":
            return await self._projects()

        # default — if there's an identifier in the text, read it; else list mine
        if spec.get("identifier"):
            return await self._read(spec)
        return await self._list_mine(spec)

    # ----- intents -----

    async def _list_mine(self, spec: dict[str, Any]) -> AgentResult:
        status = (spec.get("status") or "active").strip() or "active"
        try:
            issues = await linear.list_my_issues(status=status, limit=25)
        except Exception as e:
            return AgentResult(text=f"linear request failed. {e}", error=str(e))
        if not issues:
            return AgentResult(text=f"no {status} linear issues assigned to you.")
        lines = [f"{len(issues)} {status} issue{'s' if len(issues) != 1 else ''} assigned to you:"]
        for i in issues:
            pri = ["", " ▲▲▲", " ▲▲", " ▲", " ▼"][min(i.priority, 4)]
            lines.append(f"• {i.identifier} [{i.state}]{pri}  {i.title[:80]}")
        return AgentResult(
            text="\n".join(lines),
            tool_calls=[{"tool": "linear.list", "args": {"status": status},
                         "result": [asdict(x) for x in issues]}],
        )

    async def _search(self, spec: dict[str, Any], user_text: str) -> AgentResult:
        q = (spec.get("query") or "").strip() or user_text
        try:
            issues = await linear.search_issues(q, limit=15)
        except Exception as e:
            return AgentResult(text=f"linear search failed. {e}", error=str(e))
        if not issues:
            return AgentResult(text=f"no linear issues matching `{q}`.")
        lines = [f"{len(issues)} hit{'s' if len(issues) != 1 else ''}: {q}"]
        for i in issues:
            lines.append(f"• {i.identifier} [{i.state}]  {i.title[:80]}")
        return AgentResult(
            text="\n".join(lines),
            tool_calls=[{"tool": "linear.search", "args": {"query": q},
                         "result": [asdict(x) for x in issues]}],
        )

    async def _read(self, spec: dict[str, Any]) -> AgentResult:
        ident = (spec.get("identifier") or "").strip()
        if not ident:
            return AgentResult(text="which issue? give me an identifier like RO-42.")
        try:
            issue = await linear.get_issue(ident)
        except Exception as e:
            return AgentResult(text=f"linear request failed. {e}", error=str(e))
        if not issue:
            return AgentResult(text=f"no issue with identifier `{ident}`.")
        return AgentResult(
            text=f"`{issue.identifier}` — {issue.title}",
            tool_calls=[{"tool": "linear.read", "args": {}, "result": asdict(issue)}],
        )

    async def _create(self, spec: dict[str, Any], user_text: str, session_id: str) -> AgentResult:
        team_key = (spec.get("team_key") or "").strip().upper()
        title = (spec.get("title") or "").strip()
        desc = (spec.get("description") or "").strip()
        if not team_key or not title:
            return AgentResult(text="i need a team key and a title — e.g. \"new issue in RO: ship slack\".")
        action_id = await approval.open_approval(
            session_id=uuid.UUID(session_id),
            domain="linear",
            tool="linear.create_issue",
            description=f"create {team_key} issue: {title[:80]}",
            payload={"team_key": team_key, "title": title, "description": desc, "priority": 0},
            requires_approval=True,
        )
        return AgentResult(
            text=f"i'll create the issue in **{team_key}** if you approve:",
            actions_opened=[str(action_id)],
            tool_calls=[{
                "tool": "linear.create_draft",
                "args": {},
                "result": {"team_key": team_key, "title": title, "description": desc},
            }],
        )

    async def _comment(self, spec: dict[str, Any], user_text: str, session_id: str) -> AgentResult:
        ident = (spec.get("identifier") or "").strip()
        body = (spec.get("comment_body") or "").strip()
        if not ident:
            return AgentResult(text="which issue should i comment on? give me an identifier like RO-42.")
        if not body:
            # try to extract after the colon
            tail = user_text.split(":", 1)[1].strip() if ":" in user_text else ""
            body = tail
        if not body:
            return AgentResult(text="what should the comment say?")
        action_id = await approval.open_approval(
            session_id=uuid.UUID(session_id),
            domain="linear",
            tool="linear.add_comment",
            description=f"comment on {ident}",
            payload={"identifier": ident, "body": body},
            requires_approval=True,
        )
        return AgentResult(
            text=f"i'll post this on **{ident}** if you approve:",
            actions_opened=[str(action_id)],
            tool_calls=[{
                "tool": "linear.comment_draft",
                "args": {},
                "result": {"identifier": ident, "body": body},
            }],
        )

    async def _projects(self) -> AgentResult:
        try:
            projs = await linear.list_my_projects(limit=20)
        except Exception as e:
            return AgentResult(text=f"linear request failed. {e}", error=str(e))
        if not projs:
            return AgentResult(text="no linear projects visible.")
        lines = [f"{len(projs)} project{'s' if len(projs) != 1 else ''}:"]
        for p in projs:
            lines.append(f"• {p.name} [{p.state}]")
        return AgentResult(
            text="\n".join(lines),
            tool_calls=[{"tool": "linear.projects", "args": {},
                         "result": [{"name": p.name, "state": p.state, "url": p.url} for p in projs]}],
        )

    async def _classify(self, text: str) -> dict[str, Any]:
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
            return {"intent": "other"}


linear_agent = LinearAgent(name="linear", system_prompt="")
