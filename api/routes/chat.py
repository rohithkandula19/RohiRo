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
