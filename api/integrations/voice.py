"""voice — speech-to-text + text-to-speech via openai.

stt:  audio bytes -> text          (whisper-1 / gpt-4o-transcribe)
tts:  text       -> mp3 bytes      (tts-1, voice=nova)

uses the same openai key already used for embeddings. async-friendly via
httpx — we don't depend on the openai sdk to keep this lean.
"""

from __future__ import annotations

import httpx

from api.config import secrets
from api.observability.logging import log

STT_MODEL = "whisper-1"
TTS_MODEL = "tts-1"
TTS_VOICE = "nova"


def configured() -> bool:
    return bool(secrets.get("openai_api_key"))


def _headers(content_type: str | None = None) -> dict[str, str]:
    key = secrets.get("openai_api_key")
    if not key:
        raise RuntimeError(
            "voice not configured. set your openai key: `keyring set ro openai_api_key`."
        )
    h = {"Authorization": f"Bearer {key}"}
    if content_type:
        h["Content-Type"] = content_type
    return h


async def transcribe(audio: bytes, *, filename: str = "audio.webm") -> str:
    """audio bytes -> transcript text."""
    async with httpx.AsyncClient(timeout=60.0) as c:
        files = {
            "file": (filename, audio, "audio/webm"),
            "model": (None, STT_MODEL),
        }
        r = await c.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers=_headers(),
            files=files,
        )
        if r.status_code != 200:
            log.warning("whisper transcribe failed", status=r.status_code, body=r.text[:300])
            r.raise_for_status()
        data = r.json()
        return (data.get("text") or "").strip()


async def synthesize(text: str, *, voice: str = TTS_VOICE) -> bytes:
    """text -> mp3 audio bytes."""
    if not text.strip():
        return b""
    # tts has a hard cap; chunk if needed
    if len(text) > 4000:
        text = text[:4000]
    async with httpx.AsyncClient(timeout=60.0) as c:
        r = await c.post(
            "https://api.openai.com/v1/audio/speech",
            headers=_headers("application/json"),
            json={
                "model": TTS_MODEL,
                "voice": voice,
                "input": text,
                "response_format": "mp3",
            },
        )
        if r.status_code != 200:
            log.warning("tts synth failed", status=r.status_code, body=r.text[:300])
            r.raise_for_status()
        return r.content
