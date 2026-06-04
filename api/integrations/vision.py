"""claude vision wrapper.

verbs:
- describe(image_bytes, *, prompt='describe this image briefly')   -> str
- ocr(image_bytes)                                                  -> str
- describe_image_path(path, *, prompt=...)                          -> str
- describe_url(url, *, prompt=...)                                  -> str   (fetches first)

uses settings.model_default for quality; falls back to cheap on failure.
"""

from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from typing import Optional

import httpx

from api.config import settings
from api.observability.claude import claude_client
from api.observability.logging import log

DEFAULT_PROMPT = "describe what you see in this image. 2-4 short sentences. concrete."

OCR_PROMPT = (
    "extract ALL visible text from this image in reading order. "
    "preserve line breaks. no commentary; no headings; just the text."
)


def _mime_for(data: bytes, default: str = "image/png") -> str:
    # sniff magic bytes; faster + dep-free
    if len(data) < 4:
        return default
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return default


async def describe(image_bytes: bytes, *, prompt: str = DEFAULT_PROMPT) -> str:
    if not image_bytes:
        return "(empty image)"
    b64 = base64.b64encode(image_bytes).decode("ascii")
    media_type = _mime_for(image_bytes)
    messages = [{
        "role": "user",
        "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
            {"type": "text", "text": prompt},
        ],
    }]
    try:
        resp = await claude_client.message(
            model=settings.model_default,
            messages=messages,
            max_tokens=1200,
            temperature=0.3,
        )
        return "".join(b.text for b in resp.content if b.type == "text").strip()
    except Exception as e:
        log.exception("vision describe failed")
        return f"(vision failed: {e})"


async def ocr(image_bytes: bytes) -> str:
    return await describe(image_bytes, prompt=OCR_PROMPT)


async def describe_image_path(path: str, *, prompt: str = DEFAULT_PROMPT) -> str:
    p = Path(path).expanduser()
    data = p.read_bytes()
    return await describe(data, prompt=prompt)


async def describe_url(url: str, *, prompt: str = DEFAULT_PROMPT) -> str:
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as c:
        r = await c.get(url)
        r.raise_for_status()
        if "image" not in r.headers.get("content-type", "").lower():
            return f"(not an image: content-type={r.headers.get('content-type','?')})"
        return await describe(r.content, prompt=prompt)
