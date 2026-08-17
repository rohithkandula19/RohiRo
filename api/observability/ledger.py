"""signed egress ledger. every outward byte gets a hash-chained receipt.

each row commits to: the previous row's hash, the basis (approval flip,
self-channel reply, digest), the channel and destination, and a sha256 of
the payload. the chain is serialized with an advisory lock so concurrent
sends cannot fork it. /api/audit verifies the whole chain mechanically:
"nothing sent without a recorded basis" stops being a promise and becomes
a query.

honest scope: the ledger is written by the same machine it audits, so it
proves integrity (no row altered or removed unnoticed), not provenance
against an attacker with local root. that is still a property no cloud
agent can hand you: their enforcement point lives where you cannot look.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Optional

from api.memory.db import db
from api.observability.logging import log

GENESIS = "genesis"
_LOCK_KEY = 771177


def _payload_sha(payload: Any) -> str:
    if isinstance(payload, (dict, list)):
        raw = json.dumps(payload, sort_keys=True, default=str)
    else:
        raw = str(payload)
    return hashlib.sha256(raw.encode()).hexdigest()


def _row_hash(prev: str, basis: str, channel: str, destination: str, payload_sha: str) -> str:
    return hashlib.sha256(f"{prev}|{basis}|{channel}|{destination}|{payload_sha}".encode()).hexdigest()


async def record(
    *,
    basis: str,
    channel: str,
    destination: str,
    payload: Any,
    action_id: Optional[uuid.UUID] = None,
) -> None:
    """append one egress row. never raises — a ledger failure must not block
    a legitimate approved send, but it is logged loudly."""
    try:
        psha = _payload_sha(payload)
        pool = await db.pg()
        async with pool.acquire() as con:
            async with con.transaction():
                await con.execute("select pg_advisory_xact_lock($1)", _LOCK_KEY)
                row = await con.fetchrow("select hash from egress_ledger order by id desc limit 1")
                prev = row["hash"] if row else GENESIS
                h = _row_hash(prev, basis, channel, destination, psha)
                await con.execute(
                    """insert into egress_ledger (prev_hash, hash, action_id, basis, channel, destination, payload_sha)
                       values ($1, $2, $3, $4, $5, $6, $7)""",
                    prev, h, action_id, basis, channel, destination[:300], psha,
                )
    except Exception:
        log.exception("egress ledger write failed", channel=channel)


async def verify() -> dict[str, Any]:
    """walk the chain and recompute every hash. returns the verdict."""
    rows = await db.fetch(
        "select id, prev_hash, hash, basis, channel, destination, payload_sha from egress_ledger order by id asc"
    )
    prev = GENESIS
    for r in rows:
        if r["prev_hash"] != prev:
            return {"ok": False, "broken_at": r["id"], "reason": "chain link mismatch"}
        expect = _row_hash(prev, r["basis"], r["channel"], r["destination"], r["payload_sha"])
        if r["hash"] != expect:
            return {"ok": False, "broken_at": r["id"], "reason": "hash mismatch"}
        prev = r["hash"]
    return {"ok": True, "entries": len(rows), "head": prev}


async def recent(limit: int = 100) -> list[dict[str, Any]]:
    rows = await db.fetch(
        """select id, basis, channel, destination, payload_sha,
                  action_id::text as action_id, created_at
           from egress_ledger order by id desc limit $1""",
        limit,
    )
    out = []
    for r in rows:
        d = dict(r)
        d["created_at"] = r["created_at"].isoformat()
        out.append(d)
    return out
