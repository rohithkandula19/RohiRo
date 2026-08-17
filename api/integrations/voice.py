"""voice — speech-to-text + text-to-speech. local first, api fallback.

stt: local whisper (small.en default) in a one-worker process pool, so a
     cpu-heavy transcription can never stall the event loop that runs the
     listeners and scheduler. the worker process caches the model; a watchdog
     shuts the pool down after 10 idle minutes, which frees the ~500mb model.
     falls back to the openai api when local whisper or ffmpeg is missing.
tts: openai tts when the key exists (mp3), otherwise macos `say` piped
     through afconvert (m4a). synthesize returns (bytes, mime) so routes can
     set the honest content type.

audio stays on the machine whenever local pieces are present, per spec.
"""

from __future__ import annotations

import asyncio
import importlib.util
import shutil
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Optional

import httpx

from api.config import secrets
from api.observability.logging import log

STT_MODEL_API = "whisper-1"
TTS_MODEL = "tts-1"
TTS_VOICE = "nova"
LOCAL_WHISPER_MODEL = "small.en"
IDLE_UNLOAD_S = 600

_pool: Optional[ProcessPoolExecutor] = None
_pool_last_used: float = 0.0
_watchdog_started = False
_pool_lock = asyncio.Lock()


def _local_stt_available() -> bool:
    return importlib.util.find_spec("whisper") is not None and shutil.which("ffmpeg") is not None


def _api_available() -> bool:
    return bool(secrets.get("openai_api_key"))


def configured() -> bool:
    """voice works if either the local pipeline or the api is available."""
    return _local_stt_available() or _api_available()


def config_hint() -> str:
    return (
        "voice not configured: install ffmpeg (`brew install ffmpeg`) for local "
        "whisper, or `keyring set ro openai_api_key` for the api path"
    )


# ----- local whisper in a process pool -----


def _worker_transcribe(model_name: str, audio: bytes, suffix: str) -> str:
    """runs inside the pool worker. caches the model as a process global."""
    global _worker_model  # noqa: PLW0603
    import whisper  # imported in the worker, not the api process

    try:
        _worker_model  # type: ignore[name-defined]
    except NameError:
        _worker_model = whisper.load_model(model_name)  # type: ignore[assignment]

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as f:
        f.write(audio)
        f.flush()
        result = _worker_model.transcribe(f.name, fp16=False)  # type: ignore[attr-defined]
    return (result.get("text") or "").strip()


async def _get_pool() -> ProcessPoolExecutor:
    global _pool, _pool_last_used, _watchdog_started
    async with _pool_lock:
        if _pool is None:
            _pool = ProcessPoolExecutor(max_workers=1)
            log.info("voice: whisper pool started", model=LOCAL_WHISPER_MODEL)
        _pool_last_used = time.monotonic()
        if not _watchdog_started:
            _watchdog_started = True
            asyncio.get_running_loop().create_task(_pool_watchdog())
        return _pool


async def _pool_watchdog() -> None:
    """shut the pool down after idle time. frees the model's memory."""
    global _pool, _watchdog_started
    while True:
        await asyncio.sleep(60)
        async with _pool_lock:
            if _pool is not None and time.monotonic() - _pool_last_used > IDLE_UNLOAD_S:
                _pool.shutdown(wait=False, cancel_futures=False)
                _pool = None
                log.info("voice: whisper pool unloaded after idle")
            if _pool is None:
                _watchdog_started = False
                return


async def _transcribe_local(audio: bytes, filename: str) -> str:
    suffix = Path(filename).suffix or ".webm"
    pool = await _get_pool()
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(pool, _worker_transcribe, LOCAL_WHISPER_MODEL, audio, suffix)


# ----- api fallbacks -----


def _headers(content_type: str | None = None) -> dict[str, str]:
    key = secrets.get("openai_api_key")
    if not key:
        raise RuntimeError(config_hint())
    h = {"Authorization": f"Bearer {key}"}
    if content_type:
        h["Content-Type"] = content_type
    return h


async def _transcribe_api(audio: bytes, filename: str) -> str:
    async with httpx.AsyncClient(timeout=60.0) as c:
        files = {
            "file": (filename, audio, "audio/webm"),
            "model": (None, STT_MODEL_API),
        }
        r = await c.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers=_headers(),
            files=files,
        )
        if r.status_code != 200:
            log.warning("api transcribe failed", status=r.status_code, body=r.text[:300])
            r.raise_for_status()
        data = r.json()
        return (data.get("text") or "").strip()


# ----- public surface -----


async def transcribe(audio: bytes, *, filename: str = "audio.webm") -> str:
    """audio bytes -> transcript. local whisper first, api fallback."""
    if _local_stt_available():
        try:
            return await _transcribe_local(audio, filename)
        except Exception:
            log.exception("local whisper failed, trying api fallback")
    if _api_available():
        return await _transcribe_api(audio, filename)
    raise RuntimeError(config_hint())


async def synthesize(text: str, *, voice: str = TTS_VOICE) -> tuple[bytes, str]:
    """text -> (audio bytes, mime type). openai tts if keyed, else local say."""
    if not text.strip():
        return b"", "audio/mpeg"
    if len(text) > 4000:
        text = text[:4000]

    if _api_available():
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
            return r.content, "audio/mpeg"

    return await _synthesize_say(text)


async def _synthesize_say(text: str) -> tuple[bytes, str]:
    """macos `say` -> aiff -> afconvert -> m4a. fully local."""
    with tempfile.TemporaryDirectory() as d:
        aiff = Path(d) / "out.aiff"
        m4a = Path(d) / "out.m4a"
        p1 = await asyncio.create_subprocess_exec(
            "say", "-o", str(aiff), text,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(p1.wait(), timeout=30)
        if p1.returncode != 0 or not aiff.exists():
            raise RuntimeError("local tts (say) failed")
        p2 = await asyncio.create_subprocess_exec(
            "afconvert", str(aiff), str(m4a), "-f", "m4af", "-d", "aac",
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(p2.wait(), timeout=30)
        if p2.returncode != 0 or not m4a.exists():
            raise RuntimeError("local tts (afconvert) failed")
        return m4a.read_bytes(), "audio/mp4"
