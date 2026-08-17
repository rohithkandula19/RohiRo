"""shared inbound gateway. every chat channel routes through here.

- one stable session per (channel, chat_key), so conversations keep context
  across turns instead of starting amnesiac every message.
- everything goes through run_supervisor: classification, memory injection,
  traces, and the approval gate all apply on the highest-volume paths.
- replies back to the ro channel itself send directly. texting you back in
  your own channel is a write to your own system under the house rules.
  anything addressed to other people stays behind the approval gate inside
  the agents.
- sent-text tracking: the ro channel on imessage is usually the self chat,
  where ro's own replies land in chat.db indistinguishable from yours
  (is_from_me cannot discriminate two senders on one apple id). we record a
  hash of everything the gateway sends and skip those rows on poll.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any, Awaitable, Callable, Optional

from api.memory.db import db
from api.observability import budget
from api.observability.logging import log
from api.supervisor import run_supervisor

SENT_TTL_MINUTES = 30


async def session_for(channel: str, chat_key: str) -> uuid.UUID:
    """stable session per chat. upsert, returns the same uuid every time."""
    row = await db.fetchrow(
        """insert into channel_sessions (channel, chat_key) values ($1, $2)
           on conflict (channel, chat_key) do update set chat_key = excluded.chat_key
           returning session_id""",
        channel, chat_key,
    )
    return row["session_id"]


def _sent_key(channel: str, chat_key: str, text: str) -> str:
    digest = hashlib.sha256(f"{channel}|{chat_key}|{text.strip()}".encode()).hexdigest()[:32]
    return f"sent:{digest}"


async def record_sent(channel: str, chat_key: str, text: str) -> None:
    await db.execute(
        "insert into seen_keys (source, external_id) values ('gateway_sent', $1) on conflict do nothing",
        _sent_key(channel, chat_key, text),
    )


async def was_recently_sent(channel: str, chat_key: str, text: str) -> bool:
    row = await db.fetchrow(
        """select 1 from seen_keys
           where source = 'gateway_sent' and external_id = $1
             and first_seen_at > now() - make_interval(mins => $2)""",
        _sent_key(channel, chat_key, text), SENT_TTL_MINUTES,
    )
    return row is not None


async def _local_turn(session_id: uuid.UUID, text: str) -> str:
    """a vault or airgap turn: local model only, memory rows tainted vault.

    honest degradation: no tools, no cloud brain. the content never leaves
    the machine, including its embedding (lane check zeroes it).
    """
    from api.observability import llm_local

    history = await db.fetch(
        """select role, body from conversations
           where session_id = $1 and role in ('user','assistant')
           order by created_at desc limit 6""",
        session_id,
    )
    context = "\n".join(f"{r['role']}: {r['body'][:500]}" for r in reversed(list(history)))
    system = (
        "you are ro, a private local assistant. this conversation is in the "
        "vault lane: you run fully on-device with no tools. be concise and "
        "useful; if the user needs an action taken, tell them to ask outside "
        "the vault lane."
    )
    reply = await llm_local.chat(
        system=system,
        user=(f"recent turns:\n{context}\n\nuser: {text}" if context else text),
        max_tokens=400,
    )
    if not reply:
        reply = (
            "vault lane: the local model is not available (set the "
            "ollama_model preference and start ollama). nothing was sent to "
            "any cloud api."
        )
    for role, body in (("user", text), ("assistant", reply)):
        try:
            await db.execute(
                "insert into conversations (session_id, role, body, vault) values ($1, $2, $3, true)",
                session_id, role, body[:8000],
            )
        except Exception:
            log.warning("vault turn persist failed")
    return reply


async def handle_inbound(
    *,
    channel: str,
    chat_key: str,
    text: str,
    reply: Optional[Callable[[str], Awaitable[Any]]] = None,
) -> dict[str, Any]:
    """route one inbound message through the supervisor and reply in-channel.

    `reply` sends text back to the ro channel (direct, not approval-gated,
    because the recipient is you). pass None to suppress in-channel replies
    (email keeps its draft-and-approve flow).
    """
    session_id = await session_for(channel, chat_key)

    # event triggers: fire matching playbooks in the background before the
    # conversational turn, so trigger work never delays the reply.
    try:
        from api import triggers
        await triggers.match_and_fire(channel, text)
    except Exception:
        log.warning("trigger matching failed", channel=channel)

    # lanes: vault sources and airgap mode run on the local tier only.
    from api.observability import lanes
    lane = await lanes.lane_for_inbound(channel, chat_key)
    if lane != "vault" and await lanes.airgap_on():
        lane = "vault"  # airgap processes everything as local-only
    lanes.set_lane(lane)

    budget.set_run(f"channel:{channel}")
    if lane == "vault":
        out = await _local_turn(session_id, text)
    else:
        try:
            result = await run_supervisor(session_id=session_id, user_text=text)
            out = (result.get("text") or "").strip()
        except Exception as e:
            log.exception("gateway supervisor run failed", channel=channel)
            out = f"(ro hit an error: {e})"

    if reply is not None and out:
        try:
            await record_sent(channel, chat_key, out)
            from api.observability import ledger
            await ledger.record(
                basis="self-channel", channel=channel, destination=chat_key, payload=out,
            )
            await reply(out)
        except Exception:
            log.exception("gateway reply failed", channel=channel)

    return {"session_id": str(session_id), "text": out}
