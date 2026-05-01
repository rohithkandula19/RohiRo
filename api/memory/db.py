"""postgres pool + redis connection. one of each, lazy init."""

from __future__ import annotations

from typing import Any, Optional

import asyncpg
import redis.asyncio as aioredis

from api.config import settings
from api.observability.logging import log


class _DB:
    def __init__(self) -> None:
        self._pg_pool: Optional[asyncpg.Pool] = None
        self._redis: Optional[aioredis.Redis] = None

    async def pg(self) -> asyncpg.Pool:
        if self._pg_pool is None:
            log.info("opening postgres pool")
            self._pg_pool = await asyncpg.create_pool(
                settings.postgres_url,
                min_size=1,
                max_size=10,
                init=_init_conn,
            )
        return self._pg_pool

    def redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        return self._redis

    async def close(self) -> None:
        if self._pg_pool is not None:
            await self._pg_pool.close()
        if self._redis is not None:
            await self._redis.aclose()

    async def fetch(self, query: str, *args: Any) -> list[asyncpg.Record]:
        pool = await self.pg()
        async with pool.acquire() as con:
            return await con.fetch(query, *args)

    async def fetchrow(self, query: str, *args: Any) -> Optional[asyncpg.Record]:
        pool = await self.pg()
        async with pool.acquire() as con:
            return await con.fetchrow(query, *args)

    async def fetchval(self, query: str, *args: Any) -> Any:
        pool = await self.pg()
        async with pool.acquire() as con:
            return await con.fetchval(query, *args)

    async def execute(self, query: str, *args: Any) -> str:
        pool = await self.pg()
        async with pool.acquire() as con:
            return await con.execute(query, *args)


async def _init_conn(con: asyncpg.Connection) -> None:
    # register pgvector codec so we can pass python lists as vectors.
    try:
        from pgvector.asyncpg import register_vector  # type: ignore

        await register_vector(con)
    except Exception as e:
        log.warning("pgvector codec not registered", error=str(e))


db = _DB()
