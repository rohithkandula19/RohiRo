"""approval state machine against real postgres. the most-tested path.

these run only when the local stack is up (docker compose up -d). without
postgres they skip cleanly, same as the evals without a key.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

pytestmark = pytest.mark.asyncio


async def _pg_up() -> bool:
    try:
        from api.memory.db import db
        await asyncio.wait_for(db.pg(), timeout=3)
        # ensure the new ddl exists (idempotent)
        import pathlib
        schema = pathlib.Path(__file__).resolve().parents[2] / "api" / "memory" / "schema.sql"
        pool = await db.pg()
        async with pool.acquire() as con:
            await con.execute(schema.read_text())
        return True
    except Exception:
        return False


@pytest.fixture()
async def pg():
    if not await _pg_up():
        pytest.skip("postgres not reachable — start the stack: docker compose up -d")
    from api.memory.db import db
    yield db


async def _open(db, tool="imessage.send", payload=None) -> uuid.UUID:
    from api.supervisor import approval
    return await approval.open_approval(
        session_id=uuid.uuid4(),
        domain="comms",
        tool=tool,
        description="test action",
        payload=payload or {"handle": "self", "body": "hello"},
    )


async def test_decide_is_cas(pg) -> None:
    from api.supervisor import approval
    aid = await _open(pg)
    first = await approval.decide(aid, decision="approved")
    second = await approval.decide(aid, decision="approved")
    assert first == "applied"
    assert second == "already_approved"


async def test_concurrent_double_approve_single_apply(pg) -> None:
    from api.supervisor import approval
    aid = await _open(pg)
    results = await asyncio.gather(
        approval.decide(aid, decision="approved"),
        approval.decide(aid, decision="approved"),
    )
    assert sorted(results) == ["already_approved", "applied"]


async def test_claim_for_execute_exactly_once(pg) -> None:
    from api.supervisor import approval
    aid = await _open(pg)
    await approval.decide(aid, decision="approved")
    claims = await asyncio.gather(
        approval.claim_for_execute(aid),
        approval.claim_for_execute(aid),
    )
    winners = [c for c in claims if c is not None]
    assert len(winners) == 1


async def test_edited_path_executes_edited_body_once(pg) -> None:
    """edited decisions are approvable and run the edited text exactly once."""
    from unittest.mock import AsyncMock, patch
    from api.supervisor import approval, execute as execute_mod

    aid = await _open(pg, payload={"handle": "self", "body": "original"})
    outcome = await approval.decide(aid, decision="edited", edit_note="edited text")
    assert outcome == "applied"

    with patch("api.supervisor.execute.imsg.send_message", new=AsyncMock(return_value=True)) as send:
        result = await execute_mod.execute(aid)
        assert result["ok"] is True
        send.assert_awaited_once()
        assert send.await_args.args[1] == "edited text"

        # second execute cannot double-send
        result2 = await execute_mod.execute(aid)
        assert result2["ok"] is False
        send.assert_awaited_once()


async def test_execute_fails_closed_without_decision(pg) -> None:
    from api.supervisor import execute as execute_mod
    aid = await _open(pg)
    result = await execute_mod.execute(aid)
    assert result["ok"] is False
    assert "pending" in result["error"]


async def test_card_fidelity_handle_key(pg) -> None:
    """what the card says is what executes: describe reads the same key
    dispatch uses."""
    from api.supervisor.execute import _describe
    desc = _describe("imessage.send", {"handle": "+15551234567", "body": "yo"}, {})
    assert "+15551234567" in desc


async def test_channel_sessions_stable(pg) -> None:
    from api.listeners import gateway
    a = await gateway.session_for("imessage", "self")
    b = await gateway.session_for("imessage", "self")
    c = await gateway.session_for("telegram", "123")
    assert a == b
    assert a != c


async def test_sent_tracking_roundtrip(pg) -> None:
    from api.listeners import gateway
    text = f"unique reply {uuid.uuid4()}"
    assert not await gateway.was_recently_sent("imessage", "self", text)
    await gateway.record_sent("imessage", "self", text)
    assert await gateway.was_recently_sent("imessage", "self", text)


async def test_budget_cap_refuses(pg) -> None:
    from api.observability import budget
    # set a tiny cap, burn it, expect refusal
    await pg.execute(
        """insert into preferences (key, value) values ($1, $2)
           on conflict (key) do update set value = excluded.value""",
        budget.BUDGET_KEY, json.dumps(10),
    )
    await pg.execute(
        "insert into spend_log (run_label, model, input_tokens, output_tokens) values ('test', 'm', 100, 100)"
    )
    allowed, why = await budget.allow_run("test")
    assert not allowed
    # clean up the cap so other tests and dev use are unaffected
    await pg.execute("delete from preferences where key = $1", budget.BUDGET_KEY)
    await pg.execute("delete from spend_log where run_label = 'test'")
