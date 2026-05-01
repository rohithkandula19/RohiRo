"""memory sub-agent.

handles direct memory crud through the supervisor. internal-only writes,
no approval needed (deletes are still soft where it matters).
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from api.agents.base import Agent, AgentResult
from api.config import settings
from api.memory.db import db
from api.memory.embeddings import embed
from api.memory.retrieval import get_profile_body
from api.observability.claude import claude_client

SYSTEM = """you handle ro's memory. profile, contacts, projects, decisions,
preferences, and the conversation log.

reply with json that has shape: {"action": "...", "args": {...}, "say": "what to tell ro"}.

valid actions:
- read_profile
- update_profile_section: {section: "fitness", body: "..."}
- search: {q: "..."}
- add_contact: {name, email, role, company, notes}
- log_decision: {title, body, tags}
- set_preference: {key, value}
- list_decisions: {tag?: "..."}

if it's just a read or chat, action="read" with a `say` only.
"""


class MemoryAgent(Agent):
    async def run(self, *, session_id: str, user_text: str, context: dict[str, Any]) -> AgentResult:
        profile = await get_profile_body()
        msg_system = SYSTEM + "\n\n## current profile\n\n" + (profile or "(empty)")
        try:
            raw = await self._ask(
                system=msg_system,
                messages=[{"role": "user", "content": user_text}],
                model=settings.model_default,
                max_tokens=600,
                temperature=0.0,
            )
        except Exception as e:  # noqa: BLE001
            return AgentResult(text="", error=f"memory agent failed: {e}")

        spec = _parse(raw)
        action = spec.get("action", "read")
        args = spec.get("args", {}) or {}
        say = (spec.get("say") or "").strip()

        try:
            outcome = await _dispatch(action, args)
        except Exception as e:  # noqa: BLE001
            return AgentResult(text=say, error=str(e))

        if not say:
            say = outcome.get("say", "done.")
        return AgentResult(text=say, tool_calls=[{"action": action, "args": args, "result": outcome}])


def _parse(raw: str) -> dict[str, Any]:
    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:]
    try:
        return json.loads(s)
    except Exception:
        return {"action": "read", "say": raw[:600]}


async def _dispatch(action: str, args: dict[str, Any]) -> dict[str, Any]:
    if action in {"read", "read_profile"}:
        body = await get_profile_body()
        return {"say": body or "profile is empty.", "profile": body}

    if action == "update_profile_section":
        section = (args.get("section") or "").strip()
        body = (args.get("body") or "").strip()
        if not section or not body:
            raise ValueError("section and body required")
        existing = await get_profile_body()
        new_body = _replace_section(existing, section, body)
        await db.execute("update profile set body = $1 where id = 1", new_body)
        return {"say": f"updated section: {section}"}

    if action == "search":
        q = args.get("q") or ""
        from api.memory.retrieval import retrieve_relevant

        hits = await retrieve_relevant(q, limit=8)
        return {"say": f"found {len(hits)} hits", "hits": hits}

    if action == "add_contact":
        await db.execute(
            "insert into contacts (name, email, role, company, notes) values ($1,$2,$3,$4,$5)",
            args.get("name"),
            args.get("email"),
            args.get("role"),
            args.get("company"),
            args.get("notes"),
        )
        return {"say": f"added {args.get('name','contact')}."}

    if action == "log_decision":
        title = args.get("title") or "decision"
        body = args.get("body") or ""
        tags = args.get("tags") or []
        await db.execute(
            "insert into decisions (title, body, tags) values ($1,$2,$3)",
            title,
            body,
            tags,
        )
        return {"say": f"logged: {title}"}

    if action == "set_preference":
        key = args.get("key")
        value = args.get("value")
        if not key:
            raise ValueError("key required")
        await db.execute(
            "insert into preferences (key, value) values ($1, $2) on conflict (key) do update set value = excluded.value, updated_at = now()",
            key,
            json.dumps(value),
        )
        return {"say": f"saved preference: {key}"}

    if action == "list_decisions":
        tag = args.get("tag")
        if tag:
            rows = await db.fetch("select title, body from decisions where $1 = any(tags) order by decided_at desc limit 20", tag)
        else:
            rows = await db.fetch("select title, body from decisions order by decided_at desc limit 20")
        return {"say": f"{len(rows)} decisions", "rows": [dict(r) for r in rows]}

    raise ValueError(f"unknown memory action: {action}")


def _replace_section(profile: str, section: str, body: str) -> str:
    """find a markdown section starting with '## <section>' and replace its body.

    if not found, append at the end.
    """

    lines = profile.splitlines()
    out: list[str] = []
    i = 0
    found = False
    target = f"## {section.lower()}"
    while i < len(lines):
        line = lines[i]
        if line.strip().lower() == target:
            found = True
            out.append(line)
            out.append(body.strip())
            i += 1
            # skip until next ## or end
            while i < len(lines) and not lines[i].lstrip().startswith("## "):
                i += 1
            continue
        out.append(line)
        i += 1
    if not found:
        if out and out[-1].strip() != "":
            out.append("")
        out.append(f"## {section.lower()}")
        out.append(body.strip())
    return "\n".join(out) + ("\n" if profile.endswith("\n") else "")


memory_agent = MemoryAgent(name="memory", system_prompt=SYSTEM)
