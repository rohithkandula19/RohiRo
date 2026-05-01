"""live trace stream.

phase 1: subscribes to a redis pubsub channel 'ro:trace' and forwards events.
the supervisor publishes to that channel for every stage. the /overview page
listens via EventSource and renders the live trace card.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from api.memory.db import db

router = APIRouter()


@router.get("/stream")
async def trace_stream() -> EventSourceResponse:
    async def gen() -> "asyncio.Generator[dict, None, None]":  # noqa: F821
        redis = db.redis()
        pubsub = redis.pubsub()
        await pubsub.subscribe("ro:trace")
        try:
            yield {"event": "open", "data": json.dumps({"ok": True})}
            async for msg in pubsub.listen():
                if msg["type"] != "message":
                    continue
                data = msg.get("data") or "{}"
                yield {"event": "trace", "data": data}
        finally:
            try:
                await pubsub.unsubscribe("ro:trace")
                await pubsub.close()
            except Exception:
                pass

    return EventSourceResponse(gen())
