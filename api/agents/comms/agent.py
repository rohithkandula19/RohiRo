"""comms sub-agent.

drafts replies. opens an action_log row for the supervisor's approval gate.
no real send happens until the user approves and the supervisor calls execute().

phase 3 wires gmail mcp here. for now, a tool stub keeps the flow honest.
"""

from __future__ import annotations

import uuid
from typing import Any

from api.agents.base import Agent, AgentResult
from api.config import settings
from api.memory.retrieval import get_profile_body
from api.observability.claude import claude_client
from api.supervisor import approval

SYSTEM = """you draft messages for ro across email, slack, imessage, telegram.

ro's voice: direct, warm, short sentences. no em dashes. sentence case.
no corporate filler. no "i hope this helps". no "let me know if you need anything".

draft only. never claim it's sent. never invent thread context. when ro asks
you to reply to something, draft as if ro is writing, not as if you are.

return only the body of the message, nothing else, no preamble."""


class CommsAgent(Agent):
    async def run(self, *, session_id: str, user_text: str, context: dict[str, Any]) -> AgentResult:
        profile = await get_profile_body()
        retrieved = context.get("retrieved", []) or []
        ctx_lines = "\n".join(f"- {r.get('body','')[:240]}" for r in retrieved)
        sys = SYSTEM
        if profile.strip():
            sys += "\n\n## ro's profile\n\n" + profile.strip()
        if ctx_lines:
            sys += "\n\n## relevant context\n\n" + ctx_lines

        try:
            draft = await self._ask(
                system=sys,
                messages=[{"role": "user", "content": user_text}],
                model=settings.model_default,
                max_tokens=600,
                temperature=0.6,
            )
        except Exception as e:  # noqa: BLE001
            return AgentResult(text="", error=f"comms agent failed: {e}")

        if not draft.strip():
            return AgentResult(text="(no draft produced)")

        action_id = await approval.open_approval(
            session_id=uuid.UUID(session_id),
            domain="comms",
            tool="gmail.send",
            description=user_text[:120],
            payload={"draft": draft, "user_request": user_text},
            requires_approval=True,
        )
        return AgentResult(
            text=f"drafted. waiting on your ok before i send.\n\n---\n{draft}",
            actions_opened=[str(action_id)],
            tool_calls=[{"tool": "gmail.draft", "args": {"length": len(draft)}}],
        )


comms_agent = CommsAgent(name="comms", system_prompt=SYSTEM)
