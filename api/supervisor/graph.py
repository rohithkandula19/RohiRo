"""supervisor graph.

nodes: intake, memory_inject, classify, plan, dispatch, synthesize, log.
streams progress events the web ui consumes via sse.

phase 1 implementation: classify + answer with claude, with memory injection.
sub-agent dispatch is wired but no agents are connected yet (phase 3+).
each event the supervisor emits is a small dict the api hands to the client.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from api.config import settings
from api.memory import db, embed
from api.memory.retrieval import retrieve_relevant, get_profile_body
from api.memory.tree import write_event as tree_write
from api.observability.claude import claude_client
from api.observability.logging import log
from api.supervisor.router import classify

PROMPT_PATH = Path(__file__).parent / "prompts" / "system.md"


def _system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "you are ro's personal agent. direct, warm, short."


def _build_system(profile: str, retrieved: list[dict[str, Any]]) -> str:
    base = _system_prompt()
    parts = [base]
    if profile.strip():
        parts.append("## profile\n\n" + profile.strip())

    # split: tree hits get their own prominent section, conversation hits go below
    tree_hits = [r for r in retrieved if r.get("source") == "memory_tree"]
    convo_hits = [r for r in retrieved if r.get("source") != "memory_tree"]

    if tree_hits:
        blocks = []
        for r in tree_hits:
            label = r.get("label", "")
            blocks.append(f"### {label}\n{r.get('body','')[:1400]}")
        parts.append("## what ro has been doing\n\n" + "\n\n".join(blocks))

    if convo_hits:
        ctx = "\n\n".join(
            f"- ({r.get('source','memory')}) {r.get('body','')[:400]}"
            for r in convo_hits
        )
        parts.append("## relevant past exchanges\n\n" + ctx)

    parts.append("## now\n\n" + datetime.now(tz=timezone.utc).isoformat())
    return "\n\n".join(parts)


async def _persist_turn(session_id: uuid.UUID, role: str, body: str, meta: dict[str, Any]) -> None:
    if not body.strip():
        return
    try:
        emb = await embed(body)
    except Exception:
        emb = None
    await db.execute(
        "insert into conversations (session_id, role, body, embedding, metadata) "
        "values ($1, $2, $3, $4, $5)",
        session_id,
        role,
        body,
        emb,
        json.dumps(meta),
    )


async def stream_supervisor(
    *,
    session_id: uuid.UUID,
    user_text: str,
    history: list[dict[str, str]] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """yield trace events. last event has type='final' with the response."""

    history = history or []
    started = time.monotonic()
    yield {"type": "stage", "name": "intake", "text": "got it"}

    yield {"type": "stage", "name": "memory", "text": "pulling profile and recent context"}
    profile = await get_profile_body()
    retrieved = await retrieve_relevant(user_text, limit=6)
    if retrieved:
        yield {
            "type": "trace",
            "kind": "memory.retrieved",
            "count": len(retrieved),
        }

    yield {"type": "stage", "name": "classify", "text": "figuring out the domain"}
    routing = await classify(user_text)
    yield {"type": "trace", "kind": "classify", "domains": routing["domains"], "needs_action": routing["needs_action"]}

    # dispatch to a sub-agent if the request needs an action.
    delegated = await _maybe_dispatch(
        session_id=session_id,
        user_text=user_text,
        routing=routing,
        retrieved=retrieved,
    )
    if delegated is not None:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        await _persist_turn(session_id, "user", user_text, {"routing": routing})
        await _persist_turn(session_id, "assistant", delegated["text"], {"agent": delegated["agent"]})
        # auto-capture: ro just did something via a sub-agent
        try:
            await tree_write(
                source="chat",
                kind=f"{delegated['agent']}_run",
                summary=f"{delegated['agent']}: {user_text[:140]}",
                payload={"agent": delegated["agent"], "tools": delegated.get("tool_calls", []),
                         "actions": delegated.get("actions", [])},
            )
        except Exception:
            log.warning("tree write failed (delegated)")
        yield {"type": "trace", "kind": "agent", "agent": delegated["agent"], "actions": delegated.get("actions", [])}
        yield {
            "type": "final",
            "text": delegated["text"],
            "elapsed_ms": elapsed_ms,
            "domains": routing["domains"],
            "session_id": str(session_id),
            "actions": delegated.get("actions", []),
            "tool_calls": delegated.get("tool_calls", []),
        }
        return

    yield {"type": "stage", "name": "synthesize", "text": "drafting"}

    system = _build_system(profile, retrieved)
    messages = [{"role": h["role"], "content": h["content"]} for h in history]
    messages.append({"role": "user", "content": user_text})

    try:
        await _persist_turn(session_id, "user", user_text, {"routing": routing})
        resp = await claude_client.message(
            model=settings.model_default,
            system=system,
            messages=messages,
            max_tokens=2048,
            temperature=0.7,
            fallback_model=settings.model_cheap,
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        await _persist_turn(session_id, "assistant", text, {"model": settings.model_default})
    except Exception as e:
        log.exception("supervisor failed")
        text = f"something broke on my end. {e}"

    elapsed_ms = int((time.monotonic() - started) * 1000)
    yield {
        "type": "final",
        "text": text,
        "elapsed_ms": elapsed_ms,
        "domains": routing["domains"],
        "session_id": str(session_id),
    }


async def _maybe_dispatch(
    *,
    session_id: uuid.UUID,
    user_text: str,
    routing: dict[str, Any],
    retrieved: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """if the request maps to a sub-agent, run it and return the agent's reply.

    returns None when the supervisor should answer the user directly.
    """

    domains = routing.get("domains") or []
    primary = domains[0] if domains else "chat"

    # digest is read-only but always worth dispatching even when the classifier
    # marks it as a question (needs_action=false).
    if not routing.get("needs_action") and primary != "digest":
        return None

    if primary == "comms":
        from api.agents.comms.agent import comms_agent

        result = await comms_agent.run(
            session_id=str(session_id),
            user_text=user_text,
            context={"retrieved": retrieved},
        )
        return {
            "agent": "comms",
            "text": result.text or "(no draft)",
            "actions": result.actions_opened,
            "tool_calls": result.tool_calls,
        }

    if primary == "notion":
        from api.agents.notion.agent import notion_agent

        result = await notion_agent.run(
            session_id=str(session_id),
            user_text=user_text,
            context={"retrieved": retrieved},
        )
        return {
            "agent": "notion",
            "text": result.text or "(no result)",
            "actions": result.actions_opened,
            "tool_calls": result.tool_calls,
        }

    if primary == "files":
        from api.agents.files.agent import files_agent

        result = await files_agent.run(
            session_id=str(session_id),
            user_text=user_text,
            context={"retrieved": retrieved},
        )
        return {
            "agent": "files",
            "text": result.text or "(no result)",
            "actions": result.actions_opened,
            "tool_calls": result.tool_calls,
        }

    if primary == "digest":
        from api.digest import build_digest

        result = await build_digest()
        return {
            "agent": "digest",
            "text": result.get("markdown", "(no digest)"),
            "actions": [],
            "tool_calls": [{"tool": "digest.brief", "args": {}, "result": result.get("sections", {})}],
        }

    if primary == "linear":
        from api.agents.linear.agent import linear_agent

        result = await linear_agent.run(
            session_id=str(session_id),
            user_text=user_text,
            context={"retrieved": retrieved},
        )
        return {
            "agent": "linear",
            "text": result.text or "(no result)",
            "actions": result.actions_opened,
            "tool_calls": result.tool_calls,
        }

    if primary == "scheduler":
        from api.agents.scheduler.agent import scheduler_agent

        result = await scheduler_agent.run(
            session_id=str(session_id),
            user_text=user_text,
            context={"retrieved": retrieved},
        )
        return {
            "agent": "scheduler",
            "text": result.text or "(no result)",
            "actions": result.actions_opened,
            "tool_calls": result.tool_calls,
        }

    if primary == "actions":
        from api.agents.actions.agent import actions_agent

        result = await actions_agent.run(
            session_id=str(session_id),
            user_text=user_text,
            context={"retrieved": retrieved},
        )
        return {
            "agent": "actions",
            "text": result.text or "(no plan)",
            "actions": result.actions_opened,
            "tool_calls": result.tool_calls,
        }

    if primary == "code":
        from api.agents.code.agent import code_agent

        result = await code_agent.run(
            session_id=str(session_id),
            user_text=user_text,
            context={"retrieved": retrieved},
        )
        return {
            "agent": "code",
            "text": result.text or "(no result)",
            "actions": result.actions_opened,
            "tool_calls": result.tool_calls,
        }

    if primary == "calendar":
        from api.agents.calendar.agent import calendar_agent

        result = await calendar_agent.run(
            session_id=str(session_id),
            user_text=user_text,
            context={"retrieved": retrieved},
        )
        return {
            "agent": "calendar",
            "text": result.text or "(no result)",
            "actions": result.actions_opened,
            "tool_calls": result.tool_calls,
        }

    if primary == "memory":
        from api.agents.memory.agent import memory_agent

        result = await memory_agent.run(
            session_id=str(session_id),
            user_text=user_text,
            context={"retrieved": retrieved},
        )
        return {"agent": "memory", "text": result.text or "done.", "actions": result.actions_opened}

    return None


async def run_supervisor(*, session_id: uuid.UUID, user_text: str) -> dict[str, Any]:
    """non-streaming wrapper, used by the cli and tests."""

    final: dict[str, Any] = {"text": "", "elapsed_ms": 0}
    async for event in stream_supervisor(session_id=session_id, user_text=user_text):
        if event.get("type") == "final":
            final = event
    return final
