"""sub-agent base.

every sub-agent: name, system prompt, owned tools, run().
the supervisor passes the user text + relevant memory and gets back a small
result object with a draft, a list of opened approvals, and any tool calls made.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any

from api.observability.claude import claude_client
from api.tools.base import Tool


@dataclass
class AgentResult:
    text: str = ""
    actions_opened: list[str] = field(default_factory=list)  # action_log ids
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""


@dataclass
class Agent(abc.ABC):
    name: str
    system_prompt: str
    tools: list[Tool] = field(default_factory=list)

    @abc.abstractmethod
    async def run(self, *, session_id: str, user_text: str, context: dict[str, Any]) -> AgentResult: ...

    async def _ask(self, *, system: str, messages: list[dict[str, Any]], **kw: Any) -> str:
        resp = await claude_client.message(system=system, messages=messages, **kw)
        return "".join(b.text for b in resp.content if b.type == "text").strip()
