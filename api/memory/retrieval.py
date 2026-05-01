"""hybrid retrieval over conversations + entities.

bm25 (postgres tsvector + ts_rank) + vector cosine + recency boost.
returned as a small list of strings ready to inject into a system prompt.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from api.memory.db import db
from api.memory.embeddings import embed
from api.observability.logging import log


async def retrieve_relevant(query: str, *, limit: int = 6) -> list[dict[str, Any]]:
    if not query.strip():
        return []

    try:
        emb = await embed(query)
    except Exception as e:
        log.warning("retrieval embedding failed, falling back to bm25 only", error=str(e))
        emb = None

    rows = await _hybrid(query, emb, limit)
    return [dict(r) for r in rows]


async def _hybrid(query: str, emb: list[float] | None, limit: int) -> list[Any]:
    if emb is None:
        sql = """
        select
            'conversation' as source,
            id::text as id,
            body,
            created_at,
            ts_rank(body_tsv, plainto_tsquery('english', $1)) as score
        from conversations
        where body_tsv @@ plainto_tsquery('english', $1)
        order by score desc, created_at desc
        limit $2
        """
        return await db.fetch(sql, query, limit)

    sql = """
    with q as (select $1::text as q, $2::vector as emb),
    bm as (
        select
            'conversation' as source,
            id::text as id,
            body,
            created_at,
            ts_rank(body_tsv, plainto_tsquery('english', q.q)) as bm_score,
            null::float as vec_score
        from conversations, q
        where body_tsv @@ plainto_tsquery('english', q.q)
        order by bm_score desc
        limit 30
    ),
    vec as (
        select
            'conversation' as source,
            id::text as id,
            body,
            created_at,
            null::float as bm_score,
            1 - (embedding <=> q.emb) as vec_score
        from conversations, q
        where embedding is not null
        order by embedding <=> q.emb
        limit 30
    ),
    merged as (
        select source, id, body, created_at,
            coalesce(max(bm_score), 0) as bm_score,
            coalesce(max(vec_score), 0) as vec_score
        from (select * from bm union all select * from vec) u
        group by source, id, body, created_at
    )
    select
        source, id, body, created_at,
        bm_score, vec_score,
        (0.45 * bm_score + 0.45 * vec_score
            + 0.10 * exp(-extract(epoch from (now() - created_at)) / 1209600.0)
        ) as score
    from merged
    order by score desc
    limit $3
    """
    return await db.fetch(sql, query, emb, limit)


async def get_profile_body() -> str:
    row = await db.fetchrow("select body from profile where id = 1")
    return row["body"] if row else ""


async def recent_decisions(days: int = 30, limit: int = 10) -> list[dict[str, Any]]:
    since = datetime.now(tz=timezone.utc) - timedelta(days=days)
    rows = await db.fetch(
        "select id::text, title, body, decided_at from decisions "
        "where decided_at >= $1 order by decided_at desc limit $2",
        since,
        limit,
    )
    return [dict(r) for r in rows]
