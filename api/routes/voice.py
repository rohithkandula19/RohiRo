"""voice routes — mic → text, text → speech, full voice-loop endpoint, and a
remote-friendly /talk that does one HTTP round-trip (audio in, mp3 out) for the
iOS Shortcut."""

from __future__ import annotations

import uuid
import urllib.parse

from fastapi import APIRouter, Header, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from api.config import secrets
from api.integrations import voice as voice_int
from api.supervisor import run_supervisor

router = APIRouter()


def _check_remote_auth(authorization: str | None) -> None:
    """if RO_REMOTE_SECRET is configured in keychain, every external endpoint
    must present `Authorization: Bearer <secret>`. if not configured, endpoints
    are open (good for first-run on localhost only)."""
    expected = secrets.get("remote_secret")
    if not expected:
        return  # no secret => open mode (assume bound to 127.0.0.1)
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    given = authorization.split(None, 1)[1].strip()
    if given != expected:
        raise HTTPException(401, "bad token")


class TranscribeOut(BaseModel):
    text: str


class SpeakIn(BaseModel):
    text: str
    voice: str | None = None


class VoiceLoopOut(BaseModel):
    transcript: str
    response: str
    session_id: str


@router.post("/transcribe", response_model=TranscribeOut)
async def transcribe(audio: UploadFile) -> TranscribeOut:
    if not voice_int.configured():
        raise HTTPException(503, "voice not configured: `keyring set ro openai_api_key`")
    data = await audio.read()
    if not data:
        return TranscribeOut(text="")
    text = await voice_int.transcribe(data, filename=audio.filename or "audio.webm")
    return TranscribeOut(text=text)


@router.post("/speak")
async def speak(payload: SpeakIn) -> Response:
    if not voice_int.configured():
        raise HTTPException(503, "voice not configured: `keyring set ro openai_api_key`")
    mp3 = await voice_int.synthesize(payload.text, voice=payload.voice or "nova")
    return Response(content=mp3, media_type="audio/mpeg")


@router.post("/loop", response_model=VoiceLoopOut)
async def voice_loop(audio: UploadFile) -> VoiceLoopOut:
    """one shot: mic -> transcript -> supervisor -> response text. caller plays /speak."""
    if not voice_int.configured():
        raise HTTPException(503, "voice not configured: `keyring set ro openai_api_key`")
    data = await audio.read()
    transcript = await voice_int.transcribe(data, filename=audio.filename or "audio.webm")
    if not transcript.strip():
        return VoiceLoopOut(transcript="", response="(no speech detected)", session_id="")
    sid = uuid.uuid4()
    result = await run_supervisor(session_id=sid, user_text=transcript)
    return VoiceLoopOut(
        transcript=transcript,
        response=result.get("text", ""),
        session_id=str(sid),
    )


# ─── remote endpoints (auth-gated, designed for iOS Shortcut) ────────


@router.post("/talk")
async def talk(
    audio: UploadFile,
    authorization: str | None = Header(default=None),
) -> Response:
    """audio in, mp3 out. one round-trip for the iOS Shortcut.

    headers in the response:
      X-Ro-Transcript: <what you said>
      X-Ro-Reply:      <what ro said back, urlencoded>
    """
    _check_remote_auth(authorization)
    if not voice_int.configured():
        raise HTTPException(503, "voice not configured: `keyring set ro openai_api_key`")
    data = await audio.read()
    if not data:
        raise HTTPException(400, "no audio")
    transcript = await voice_int.transcribe(data, filename=audio.filename or "audio.m4a")
    if not transcript.strip():
        return Response(content=b"", media_type="audio/mpeg", headers={
            "X-Ro-Transcript": "",
            "X-Ro-Reply": urllib.parse.quote("(no speech detected)"),
        })
    sid = uuid.uuid4()
    result = await run_supervisor(session_id=sid, user_text=transcript)
    reply = result.get("text", "")
    mp3 = await voice_int.synthesize(reply)
    return Response(content=mp3, media_type="audio/mpeg", headers={
        "X-Ro-Transcript": urllib.parse.quote(transcript)[:1500],
        "X-Ro-Reply": urllib.parse.quote(reply)[:3000],
        "X-Ro-Session": str(sid),
    })


@router.post("/ask")
async def ask_text(
    payload: dict,
    authorization: str | None = Header(default=None),
) -> Response:
    """text in, mp3 out. for Siri 'Hey Siri, ask ro X' that already gives us text."""
    _check_remote_auth(authorization)
    if not voice_int.configured():
        raise HTTPException(503, "voice not configured: `keyring set ro openai_api_key`")
    text = (payload or {}).get("text", "").strip()
    if not text:
        raise HTTPException(400, "missing 'text'")
    sid = uuid.uuid4()
    result = await run_supervisor(session_id=sid, user_text=text)
    reply = result.get("text", "")
    mp3 = await voice_int.synthesize(reply)
    return Response(content=mp3, media_type="audio/mpeg", headers={
        "X-Ro-Reply": urllib.parse.quote(reply)[:3000],
        "X-Ro-Session": str(sid),
    })
