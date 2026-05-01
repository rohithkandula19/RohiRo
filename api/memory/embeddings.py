"""openai embeddings, batched. one wrapper, agents never see openai directly."""

from __future__ import annotations

from typing import Optional

from openai import AsyncOpenAI

from api.config import secrets, settings
from api.observability.logging import log

_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        key = secrets.get("openai_api_key")
        if not key:
            raise RuntimeError("openai_api_key missing in keychain")
        _client = AsyncOpenAI(api_key=key)
    return _client


async def embed(text: str) -> list[float]:
    out = await embed_many([text])
    return out[0]


async def embed_many(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    cleaned = [t if t.strip() else " " for t in texts]
    try:
        resp = await _get_client().embeddings.create(model=settings.model_embed, input=cleaned)
        return [d.embedding for d in resp.data]
    except Exception as e:
        log.warning("embedding failed, returning zeros", error=str(e))
        return [[0.0] * 1536 for _ in cleaned]
