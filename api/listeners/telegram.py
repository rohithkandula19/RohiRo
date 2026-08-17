"""telegram listener.

polls Telegram getUpdates every 5s (long-poll, cheap).

for each new message:
  1. if owner_id is set, ignore messages from anyone else
  2. write a raw_event so the memory tree picks it up
  3. private chats (DMs with the bot from the owner) are treated as ro
     being directly addressed → comms agent drafts a reply with approval
  4. group/channel messages are only auto-drafted when they mention ro
     ("@ro", "hey ro", "ro:")

watermark is the latest update_id, stored in seen_keys.
"""

from __future__ import annotations

import asyncio
import re
from typing import Optional

from api.integrations import telegram as tg
from api.listeners import gateway
from api.memory.db import db
from api.memory.tree import write_event as tree_write
from api.observability.logging import log

POLL_INTERVAL_S = 5
LONG_POLL_TIMEOUT_S = 25  # telegram caps at 50
MENTION_RE = re.compile(
    r"(?:(?:\bhey\s+ro\b)|(?:@ro\b)|(?:^\s*ro[\s,:!?-]))",
    re.IGNORECASE,
)


async def _get_offset() -> int:
    row = await db.fetchrow(
        "select external_id from seen_keys where source = 'telegram_listener' and external_id like 'update_id:%' order by first_seen_at desc limit 1"
    )
    if not row:
        return 0
    try:
        return int(row["external_id"].split(":", 1)[1]) + 1
    except Exception:
        return 0


async def _set_offset(update_id: int) -> None:
    await db.execute(
        """insert into seen_keys (source, external_id) values ('telegram_listener', $1)
           on conflict do nothing""",
        f"update_id:{update_id}",
    )


async def _maybe_reply(u: tg.TGUpdate) -> Optional[str]:
    """route a message that addresses ro through the gateway.

    the sender is already owner-gated by the caller. dms are the ro channel,
    so the supervisor's reply goes straight back to the chat (a write to your
    own system). group messages still need a mention.
    """
    is_dm = u.chat_kind == "private"
    has_mention = bool(MENTION_RE.search(u.text))
    if not (is_dm or has_mention):
        return None
    try:
        chat_key = str(u.chat_id)

        async def _reply(text: str) -> None:
            await tg.send_message(u.chat_id, text)

        result = await gateway.handle_inbound(
            channel="telegram", chat_key=chat_key, text=u.text, reply=_reply,
        )
        return result.get("session_id")
    except Exception:
        log.exception("telegram dispatch failed", update_id=u.update_id)
    return None


async def run_once() -> dict[str, int]:
    if not tg.configured():
        return {"skipped": 1}
    if tg.owner_id() is None:
        return {"skipped": 1, "reason_owner_unset": 1}

    offset = await _get_offset()
    updates = await tg.get_updates(offset=offset, timeout=0, limit=50)
    if not updates:
        return {"new": 0}

    owner = tg.owner_id()
    new = 0
    replies = 0
    highest = 0
    ignored_outsider = 0

    for u in updates:
        highest = max(highest, u.update_id)
        if owner is not None and u.from_id != owner:
            ignored_outsider += 1
            continue
        new += 1
        try:
            await tree_write(
                source="telegram",
                kind="received",
                actor="external",
                summary=f"telegram from {u.from_name or u.chat_title}: {u.text[:160]}",
                payload={
                    "update_id": u.update_id, "chat_id": u.chat_id,
                    "from": u.from_name, "chat": u.chat_title,
                    "kind": u.chat_kind, "text": u.text[:1500],
                },
            )
        except Exception:
            log.warning("telegram tree write failed", update_id=u.update_id)

        action_id = await _maybe_reply(u)
        if action_id:
            replies += 1

    if highest:
        await _set_offset(highest)

    out = {"new": new, "replies_drafted": replies, "highest_update_id": highest}
    if ignored_outsider:
        out["ignored_outsider"] = ignored_outsider
    return out


async def loop() -> None:
    """background task entry. uses telegram long-polling to keep it cheap."""
    await asyncio.sleep(10)

    if not tg.configured():
        log.warning("telegram listener disabled — no telegram_bot_token in keychain")
        return

    # fail closed: without an owner id, anyone who finds the bot could talk to
    # ro (claude spend, memory pollution, injection surface). refuse to start.
    if tg.owner_id() is None:
        log.error(
            "telegram listener refused to start — telegram_owner_id not set. "
            "run: keyring set ro telegram_owner_id"
        )
        return

    # warm: who is the bot?
    try:
        me = await tg.get_me()
        log.info("telegram listener started",
                 bot=me.get("username") or me.get("first_name") or "?",
                 owner_id=tg.owner_id())
    except Exception:
        log.exception("telegram get_me failed; loop will still try")

    while True:
        try:
            offset = await _get_offset()
            updates = await tg.get_updates(offset=offset, timeout=LONG_POLL_TIMEOUT_S, limit=50)
            if not updates:
                continue
            counts = await _process(updates)
            if counts.get("new"):
                log.info("telegram listener tick", **counts)
        except Exception:
            log.exception("telegram listener iteration failed")
            await asyncio.sleep(POLL_INTERVAL_S)


async def _process(updates: list[tg.TGUpdate]) -> dict[str, int]:
    """run the per-update work returned by long-poll. shares logic with run_once."""
    owner = tg.owner_id()
    new = 0
    replies = 0
    highest = 0
    ignored_outsider = 0
    for u in updates:
        highest = max(highest, u.update_id)
        if owner is not None and u.from_id != owner:
            ignored_outsider += 1
            continue
        new += 1
        try:
            await tree_write(
                source="telegram",
                kind="received",
                actor="external",
                summary=f"telegram from {u.from_name or u.chat_title}: {u.text[:160]}",
                payload={
                    "update_id": u.update_id, "chat_id": u.chat_id,
                    "from": u.from_name, "chat": u.chat_title,
                    "kind": u.chat_kind, "text": u.text[:1500],
                },
            )
        except Exception:
            log.warning("telegram tree write failed", update_id=u.update_id)

        action_id = await _maybe_reply(u)
        if action_id:
            replies += 1

    if highest:
        await _set_offset(highest)

    out = {"new": new, "replies_drafted": replies, "highest_update_id": highest}
    if ignored_outsider:
        out["ignored_outsider"] = ignored_outsider
    return out
