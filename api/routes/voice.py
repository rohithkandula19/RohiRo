"""voice route. accepts audio, runs whisper local, hands transcript to supervisor.

phase 4 wires whisper. for now, accepts text directly so the ios shortcut
can post text/transcript pairs without blocking on whisper install.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, UploadFile, Form
from pydantic import BaseModel

from api.supervisor import run_supervisor

router = APIRouter()


class VoiceOut(BaseModel):
    transcript: str
    response: str
    session_id: str


@router.post("", response_model=VoiceOut)
async def voice(text: str = Form(default=""), audio: UploadFile | None = None) -> VoiceOut:
    transcript = text or ""
    if not transcript and audio is not None:
        # phase 4 plugs whisper here. todo.
        transcript = "[audio transcription pending]"

    session_id = uuid.uuid4()
    result = await run_supervisor(session_id=session_id, user_text=transcript)
    return VoiceOut(
        transcript=transcript,
        response=result.get("text", ""),
        session_id=str(session_id),
    )
