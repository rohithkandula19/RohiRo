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
    budget.set_run(f"channel:{channel}")
    try:
        result = await run_supervisor(session_id=session_id, user_text=text)
        out = (result.get("text") or "").strip()
    except Exception as e:
        log.exception("gateway supervisor run failed", channel=channel)
        out = f"(ro hit an error: {e})"

    if reply is not None and out:
        try:
            await record_sent(channel, chat_key, out)
            await reply(out)
        except Exception:
            log.exception("gateway reply failed", channel=channel)

    return {"session_id": str(session_id), "text": out}
