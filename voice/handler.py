"""local whisper transcription.

phase 4 wires this up into the voice route. for now, exposes a function
the api route can import once whisper is loaded.
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path
from typing import Optional

_model = None


def _load() -> object:
    global _model
    if _model is not None:
        return _model
    import whisper  # type: ignore

    _model = whisper.load_model("base")
    return _model


async def transcribe(data: bytes, *, suffix: str = ".m4a") -> str:
    model = _load()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as f:
        f.write(data)
        f.flush()
        result = model.transcribe(f.name)  # type: ignore[attr-defined]
    return (result.get("text") or "").strip()
