"""notion sub-agent.

intents:
- search       "search notion for photon"
- read         "open my notes on photon"
- summarize    "summarize my notion page X"
- create       "make a new notion page titled X with body Y"      (approval)
- append       "append to my photon page: ..."                    (approval)
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from typing import Any

from api.agents.base import Agent, AgentResult
from api.config import settings
from api.integrations import notion
from api.observability.logging import log
from api.supervisor import approval

INTENT_PROMPT = """classify a request about notion. extract the parameters.

intents:
- "search"     user wants to find pages
- "read"       user wants the contents of a specific page
- "summarize"  user wants a one-paragraph summary of a page
- "create"     user wants a new page (must mention "create"/"new"/"make")
- "append"     user wants to add to an existing page
- "other"      none of the above

params (extract what's there, else empty string):
- "query":    keyword(s) for search/read/summarize/append targeting
- "title":    a clear page title if user is creating one
- "content":  the body the user wants written (verbatim if possible)

reply with ONLY a JSON object:
{"intent": "...", "query": "...", "title": "...", "content": "..."}"""


class NotionAgent(Agent):
    async def run(self, *, session_id: str, user_text: str, context: dict[str, Any]) -> AgentResult:
        if not notion.configured():
            return AgentResult(
                text=(
                    "i can't reach notion yet.\n\n"
                    "one-time setup:\n"
                    "  1. create an integration at https://www.notion.so/my-integrations\n"
                    "  2. share each page/database with the integration (•••  →  Add connections)\n"
                    "  3. `keyring set ro notion_token` and paste the integration secret"
                ),
                error="notion_not_configured",
            )

        spec = await self._classify(user_text)
        kind = spec.get("intent", "other")
        if kind == "search":
            return await self._search(spec, user_text)
        if kind == "read":
            return await self._read(spec)
        if kind == "summarize":
            return await self._summarize(spec)
        if kind == "create":
            return await self._create(spec, user_text, session_id)
        if kind == "append":
            return await self._append(spec, user_text, session_id)

        # ambiguous: search if there's a query, else default to recent
        if spec.get("query") or spec.get("title"):
            return await self._search(spec, user_text)
        return await self._search({"query": ""}, user_text)

    # ----- intents -----

    async def _search(self, spec: dict[str, Any], user_text: str) -> AgentResult:
        q = (spec.get("query") or "").strip()
        try:
            hits = await notion.search(q, limit=12)
        except Exception as e:
            return AgentResult(text=f"notion search failed. {e}", error=str(e))
        if not hits:
            return AgentResult(text=f"no notion {'pages matching `' + q + '`' if q else 'pages visible to ro'}.")
        lines = [f"{len(hits)} hit{'s' if len(hits) != 1 else ''}{(': ' + q) if q else ''}"]
        for h in hits:
            lines.append(f"• {h.icon + ' ' if h.icon else ''}{h.title}  [{h.object_kind}]")
        return AgentResult(
            text="\n".join(lines),
            tool_calls=[{
                "tool": "notion.search",
                "args": {"query": q},
                "result": [asdict(h) for h in hits],
            }],
        )

    async def _read(self, spec: dict[str, Any]) -> AgentResult:
        q = (spec.get("query") or "").strip()
        if not q:
            return AgentResult(text="which notion page should i open?")
        page = await self._find_one(q)
        if not page:
            return AgentResult(text=f"no notion page matching `{q}`.")
        try:
            content = await notion.get_page_content(page.page_id, max_chars=8000)
        except Exception as e:
            return AgentResult(text=f"couldn't read `{page.title}`. {e}", error=str(e))
        return AgentResult(
            text=f"`{page.title}` — first 8000 chars:",
            tool_calls=[{
                "tool": "notion.read",
                "args": {"page": page.title},
                "result": {"page_id": page.page_id, "title": page.title,
                           "url": page.url, "icon": page.icon, "content": content},
            }],
        )

    async def _summarize(self, spec: dict[str, Any]) -> AgentResult:
        q = (spec.get("query") or "").strip()
        if not q:
            return AgentResult(text="which page should i summarize?")
        page = await self._find_one(q)
        if not page:
            return AgentResult(text=f"no notion page matching `{q}`.")
        try:
            content = await notion.get_page_content(page.page_id, max_chars=12000)
        except Exception as e:
            return AgentResult(text=f"couldn't read `{page.title}`. {e}", error=str(e))
        if not content.strip():
            return AgentResult(text=f"`{page.title}` is empty.")
        sys = "summarize in 4-6 sentences plus 2-4 specific bullets."
        try:
            blurb = await self._ask(
                system=sys,
                messages=[{"role": "user", "content": f"page: {page.title}\n\n{content}"}],
                model=settings.model_default,
                max_tokens=600,
                temperature=0.4,
            )
        except Exception as e:
            blurb = f"(couldn't draft summary: {e})"
        return AgentResult(
            text=f"**{page.title}**\n\n{blurb}",
            tool_calls=[{
                "tool": "notion.summary",
                "args": {"page": page.title},
                "result": {"page_id": page.page_id, "title": page.title,
                           "url": page.url, "icon": page.icon, "summary": blurb},
            }],
        )

    async def _create(self, spec: dict[str, Any], user_text: str, session_id: str) -> AgentResult:
        title = (spec.get("title") or "").strip()
        content = (spec.get("content") or "").strip()
        if not title:
            return AgentResult(text="i need a title for the new notion page.")
        if not content:
            content = f"_(empty — created by ro from request: {user_text[:120]})_"

        # find a default parent: the most recent page the user has shared with ro
        try:
            hits = await notion.search("", kinds="page", limit=5)
        except Exception as e:
            return AgentResult(text=f"notion not reachable. {e}", error=str(e))
        if not hits:
            return AgentResult(
                text="no notion pages visible — ro needs at least one page shared with the integration to act as a parent.",
            )
        parent = hits[0]

        action_id = await approval.open_approval(
            session_id=uuid.UUID(session_id),
            domain="notion",
            tool="notion.create_page",
            description=f"create '{title}' under '{parent.title}'",
            payload={"parent_id": parent.page_id, "parent_title": parent.title,
                     "title": title, "body": content},
            requires_approval=True,
        )
        return AgentResult(
            text=f"i'll create the page under **{parent.title}** if you approve:",
            actions_opened=[str(action_id)],
            tool_calls=[{
                "tool": "notion.create_draft",
                "args": {},
                "result": {"parent": parent.title, "title": title,
                           "body": content, "parent_url": parent.url},
            }],
        )

    async def _append(self, spec: dict[str, Any], user_text: str, session_id: str) -> AgentResult:
        q = (spec.get("query") or "").strip()
        content = (spec.get("content") or "").strip()
        if not q or not content:
            return AgentResult(text="i need both a target page and content to append.")
        page = await self._find_one(q)
        if not page:
            return AgentResult(text=f"no notion page matching `{q}`.")
        action_id = await approval.open_approval(
            session_id=uuid.UUID(session_id),
            domain="notion",
            tool="notion.append_blocks",
            description=f"append to '{page.title}'",
            payload={"page_id": page.page_id, "page_title": page.title,
                     "page_url": page.url, "body": content},
            requires_approval=True,
        )
        return AgentResult(
            text=f"i'll append to **{page.title}** if you approve:",
            actions_opened=[str(action_id)],
            tool_calls=[{
                "tool": "notion.append_draft",
                "args": {},
                "result": {"page_title": page.title, "page_url": page.url,
                           "body": content},
            }],
        )

    # ----- helpers -----

    async def _find_one(self, q: str):
        hits = await notion.search(q, kinds="page", limit=3)
        return hits[0] if hits else None

    async def _classify(self, text: str) -> dict[str, Any]:
        try:
            raw = await self._ask(
                system=INTENT_PROMPT,
                messages=[{"role": "user", "content": text}],
                model=settings.model_cheap,
                max_tokens=240,
                temperature=0.0,
            )
            if raw.startswith("```"):
                raw = raw.strip("`")
                if raw.lower().startswith("json"):
                    raw = raw[4:]
            return json.loads(raw)
        except Exception:
            return {"intent": "other", "query": "", "title": "", "content": ""}


notion_agent = NotionAgent(name="notion", system_prompt="")
