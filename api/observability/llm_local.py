"""local model tier via ollama. free, private, sub-second.

used for the high-volume low-stakes call: classification. claude stays the
brain; ollama handles the routing when it is present. behavior:

- the preferences key 'ollama_model' names the model (e.g. llama3.2:3b).
  unset means this tier is off and nothing changes.
- reachability is probed lazily and cached for a minute, so a stopped
  ollama costs one failed probe per minute, not one per message.
- any failure falls through to claude. local is an optimization, never a
  dependency.
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

import httpx

from api.memory.db import db
from api.observability.logging import log

OLLAMA_URL = "http://127.0.0.1:11434"
PROBE_TTL_S = 60
CALL_TIMEOUT_S = 10

_probe_cache: tuple[float, bool] = (0.0, False)
_model_cache: tuple[float, Optional[str]] = (0.0, None)


async def _model() -> Optional[str]:
    global _model_cache
    now = time.monotonic()
    if now - _model_cache[0] < PROBE_TTL_S:
        return _model_cache[1]
    name: Optional[str] = None
    try:
        row = await db.fetchrow("select value from preferences where key = 'ollama_model'")
        if row:
            value = row["value"]
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except Exception:
                    pass
            name = str(value).strip() or None
    except Exception:
        name = None
    _model_cache = (now, name)
    return name


async def _reachable() -> bool:
    global _probe_cache
    now = time.monotonic()
    if now - _probe_cache[0] < PROBE_TTL_S:
        return _probe_cache[1]
    ok = False
    try:
        async with httpx.AsyncClient(timeout=2.0) as c:
            r = await c.get(f"{OLLAMA_URL}/api/tags")
            ok = r.status_code == 200
    except Exception:
        ok = False
    _probe_cache = (now, ok)
    return ok


async def available() -> bool:
    return (await _model()) is not None and await _reachable()


async def chat(*, system: str, user: str, max_tokens: int = 300) -> Optional[str]:
    """one local chat completion. returns None on any failure so callers
    fall through to claude."""
    model = await _model()
    if not model or not await _reachable():
        return None
    try:
        async with httpx.AsyncClient(timeout=CALL_TIMEOUT_S) as c:
            r = await c.post(f"{OLLAMA_URL}/api/chat", json={
                "model": model,
                "stream": False,
                "options": {"num_predict": max_tokens, "temperature": 0.0},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            })
            if r.status_code != 200:
                log.warning("ollama chat non-200", status=r.status_code)
                return None
            content = ((r.json().get("message") or {}).get("content") or "").strip()
            return content or None
    except Exception as e:
        log.warning("ollama chat failed", error=str(e)[:120])
        return None
