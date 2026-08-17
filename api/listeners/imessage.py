"""inbound imessage listener. the ro channel.

every 15s, scans chat.db for new messages in the ro channel (rowid > watermark).
the ro channel is the chat named by the `imessage_channel` keychain key: your
self chat (text your own number) or a dedicated contact. one addressing
policy, fail closed: without the key the listener refuses to start.

every message in the channel is for ro, no mention prefix needed. replies go
straight back into the channel (texting you back is a write to your own
system). loop prevention: in the self chat ro's replies land in chat.db
indistinguishable from yours (same apple id, is_from_me cannot discriminate),
so the gateway records a hash of everything it sends and the poll skips
matching rows.

watermark (highest rowid seen) persists in `seen_keys` so a restart never
replays or double-answers.
"""

from __future__ import annotations

import asyncio
import hashlib

from api.config import secrets
from api.integrations import imessage as imsg
from api.listeners import gateway
from api.memory.db import db
from api.memory.tree import write_event as tree_write
from api.observability import liveness
from api.observability.logging import log

POLL_INTERVAL_S = 15
CHANNEL = "imessage"


def _channel_key() -> str:
    return (secrets.get("imessage_channel") or "").strip()


def _guest_keys() -> list[str]:
    """guest mode: extra people allowed a limited ro. comma-separated
    handles in the imessage_guests keychain key. empty means nobody."""
    raw = (secrets.get("imessage_guests") or "").strip()
    return [g.strip() for g in raw.split(",") if g.strip()][:5]


GUEST_FRAME = (
    "(a guest, '{who}', is texting you. answer helpfully and briefly. hard "
    "rules for guests: no actions of any kind, no shell, no browser, no "
    "sends; never reveal the owner's private information, messages, "
    "schedule details, or memory contents; if asked, say that's private. "
    "general questions and small talk are fine.)\n\n"
)


async def _get_watermark() -> int:
    row = await db.fetchrow(
        "select external_id from seen_keys where source = 'imessage_listener' and external_id like 'rowid:%' order by first_seen_at desc limit 1"
    )
    if not row:
        return -1
    try:
        return int(row["external_id"].split(":", 1)[1])
    except Exception:
        return -1


async def _set_watermark(rowid: int) -> None:
    await db.execute(
        """insert into seen_keys (source, external_id) values ('imessage_listener', $1)
           on conflict do nothing""",
        f"rowid:{rowid}",
    )


async def _bootstrap_watermark(channel_key: str) -> int:
    """on first run, seed the watermark at the channel's current max rowid so
    we don't replay history."""
    msgs = await imsg.channel_messages(channel_key, since_rowid=0, limit=10000)
    max_rowid = max((m.rowid for m in msgs), default=0)
    await _set_watermark(max_rowid)
    log.info("imessage listener bootstrapped watermark", rowid=max_rowid)
    return max_rowid


async def run_once() -> dict[str, int]:
    """one poll iteration. returns counts for logging."""
    if not imsg.configured():
        return {"skipped": 1}
    channel_key = _channel_key()
    if not channel_key:
        return {"skipped": 1, "reason_channel_unset": 1}

    watermark = await _get_watermark()
    if watermark < 0:
        await _bootstrap_watermark(channel_key)
        return {"bootstrapped": 1}

    msgs = await imsg.channel_messages(channel_key, since_rowid=watermark, limit=50)
    if not msgs:
        return {"new": 0}

    new = 0
    replies = 0
    skipped_own = 0
    highest = watermark
    for m in msgs:
        highest = max(highest, m.rowid)

        # skip ro's own replies (sent-text tracking; see module docstring)
        if await gateway.was_recently_sent(CHANNEL, channel_key, m.text):
            skipped_own += 1
            continue
        new += 1

        try:
            await tree_write(
                source="imessage",
                kind="received",
                actor="external",
                summary=f"ro channel: {m.text[:160]}",
                payload={"rowid": m.rowid, "chat": m.chat_display, "text": m.text[:1500]},
            )
        except Exception:
            log.warning("imessage tree write failed", rowid=m.rowid)

        target = m.from_handle or channel_key

        async def _reply(text: str, _target: str = target) -> None:
            ok = await imsg.send_message(_target, text)
            if not ok:
                raise RuntimeError("imessage reply send failed")

        result = await gateway.handle_inbound(
            channel=CHANNEL, chat_key=channel_key, text=m.text, reply=_reply,
        )
        if result.get("text"):
            replies += 1

    await _set_watermark(highest)
    out = {"new": new, "replies": replies, "watermark": highest}
    if skipped_own:
        out["skipped_own"] = skipped_own

    guests = await _run_guests()
    if guests:
        out["guest_replies"] = guests
    return out


async def _run_guests() -> int:
    """limited ro for allowlisted guests. separate watermark per guest,
    separate sessions, no actions, no private data (instruction-framed and
    the guest session shares nothing with yours)."""
    replies = 0
    for guest in _guest_keys():
        mark_key = f"imessage_guest_{hashlib.sha256(guest.encode()).hexdigest()[:12]}"
        row = await db.fetchrow(
            "select external_id from seen_keys where source = $1 order by first_seen_at desc limit 1",
            mark_key,
        )
        mark = 0
        if row:
            try:
                mark = int(row["external_id"].split(":", 1)[1])
            except Exception:
                mark = 0
        msgs = await imsg.channel_messages(guest, since_rowid=mark, limit=10)
        if not msgs:
            continue
        highest = mark
        for m in msgs:
            highest = max(highest, m.rowid)
            if mark == 0:
                continue  # first sight is baseline, not a backlog to answer
            if await gateway.was_recently_sent(CHANNEL, guest, m.text):
                continue

            target = m.from_handle or guest

            async def _reply(text: str, _t: str = target) -> None:
                ok = await imsg.send_message(_t, text)
                if not ok:
                    raise RuntimeError("guest reply send failed")

            framed = GUEST_FRAME.format(who=m.chat_display[:60]) + m.text
            result = await gateway.handle_inbound(
                channel="imessage-guest", chat_key=guest, text=framed, reply=_reply,
            )
            if result.get("text"):
                replies += 1
        await db.execute(
            "insert into seen_keys (source, external_id) values ($1, $2) on conflict do nothing",
            mark_key, f"rowid:{highest}",
        )
    return replies


async def loop() -> None:
    """background task entry."""
    await asyncio.sleep(8)

    if not imsg.configured():
        log.warning("imessage listener disabled — chat.db not readable (grant Full Disk Access)")
        return

    # fail closed: one addressing policy. without a named ro channel we would
    # have to guess which chats may command ro, and guessing is the vuln.
    if not _channel_key():
        log.error(
            "imessage listener refused to start — imessage_channel not set. "
            "run: keyring set ro imessage_channel  (your own number, email, or a chat name)"
        )
        return

    log.info("imessage listener started", poll_s=POLL_INTERVAL_S, channel=_channel_key())
    while True:
        try:
            counts = await run_once()
            await liveness.beat("imessage_listener", ok=True)
            if counts.get("new"):
                log.info("imessage listener tick", **counts)
        except Exception as e:
            log.exception("imessage listener iteration failed")
            await liveness.beat("imessage_listener", ok=False, error=str(e))
        await asyncio.sleep(POLL_INTERVAL_S)
