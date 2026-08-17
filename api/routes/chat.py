"""chat routes. one streaming sse, one plain post for non-stream clients."""

from __future__ import annotations

import json
import uuid
from typing import Any, Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from api.supervisor import run_supervisor, stream_supervisor

router = APIRouter()


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=32_000)


class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=32_000)
    session_id: Optional[str] = None
    history: list[ChatTurn] = Field(default_factory=list, max_length=40)


class ChatOut(BaseModel):
    session_id: str
    text: str
    elapsed_ms: int


def _session(value: Optional[str]) -> uuid.UUID:
    if not value:
        return uuid.uuid4()
    try:
        return uuid.UUID(value)
    except ValueError:
        return uuid.uuid4()


@router.get("/sessions")
async def list_sessions(limit: int = 30) -> list[dict[str, Any]]:
    """recent conversations across channels, newest activity first. feeds
    the thread view."""
    from api.memory.db import db
    rows = await db.fetch(
        """select cs.channel, cs.chat_key, cs.session_id::text as session_id,
                  max(c.created_at) as last_at, count(c.id) as turns
           from channel_sessions cs
           left join conversations c on c.session_id = cs.session_id
           group by cs.channel, cs.chat_key, cs.session_id
           order by max(c.created_at) desc nulls last
           limit $1""",
        limit,
    )
    return [
        {
            "channel": r["channel"], "chat_key": r["chat_key"],
            "session_id": r["session_id"], "turns": r["turns"],
            "last_at": r["last_at"].isoformat() if r["last_at"] else None,
        }
        for r in rows
    ]


@router.get("/sessions/{session_id}/transcript")
async def session_transcript(session_id: str, limit: int = 100) -> list[dict[str, Any]]:
    """the thread: turns interleaved with the actions they opened."""
    from api.memory.db import db
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(400, "bad session id")
    turns = await db.fetch(
        """select role, body, vault, created_at from conversations
           where session_id = $1 and role in ('user','assistant','summary')
           order by created_at asc limit $2""",
        sid, limit,
    )
    actions = await db.fetch(
        """select tool, description, status, created_at from action_log
           where session_id = $1 order by created_at asc limit 50""",
        sid,
    )
    events: list[dict[str, Any]] = []
    for t in turns:
        events.append({"kind": "turn", "role": t["role"], "body": t["body"],
                       "vault": t["vault"], "at": t["created_at"].isoformat()})
    for a in actions:
        events.append({"kind": "action", "tool": a["tool"], "description": a["description"],
                       "status": a["status"], "at": a["created_at"].isoformat()})
    events.sort(key=lambda e: e["at"])
    return events


@router.post("", response_model=ChatOut)
async def chat(payload: ChatIn) -> ChatOut:
    session_id = _session(payload.session_id)
    result = await run_supervisor(session_id=session_id, user_text=payload.text)
    return ChatOut(session_id=str(session_id), text=result.get("text", ""), elapsed_ms=result.get("elapsed_ms", 0))


@router.post("/stream")
async def chat_stream(payload: ChatIn) -> EventSourceResponse:
    session_id = _session(payload.session_id)
    history = [t.model_dump() for t in payload.history]

    async def gen() -> Any:
        async for event in stream_supervisor(
            session_id=session_id,
            user_text=payload.text,
            history=history,
        ):
            yield {"event": event.get("type", "message"), "data": json.dumps(event)}

    return EventSourceResponse(gen())
