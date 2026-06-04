"""inbound imessage listener.

every 30s, scans chat.db for new inbound messages (rowid > watermark).

for each new message:
  1. write a raw_event so the memory tree picks it up
  2. if the text mentions ro ("@ro", "hey ro", "ro:" at start of message),
     run the comms agent against it — that drafts a reply and opens an
     approval card. macOS notification fires when the draft is ready.

watermark (highest rowid seen) is stored in `seen_keys` under
('imessage_listener', 'last_rowid'). first run uses the current highest
rowid so we don't backfill history.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from typing import Optional

from api.integrations import imessage as imsg
from api.memory.db import db
from api.memory.tree import write_event as tree_write
from api.observability.logging import log

POLL_INTERVAL_S = 30
MENTION_RE = re.compile(
    r"(?:(?:\bhey\s+ro\b)|(?:@ro\b)|(?:^\s*ro[\s,:!?-]))",
    re.IGNORECASE,
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


async def _bootstrap_watermark() -> int:
    """on first run, seed the watermark with the current max rowid so we don't
    replay every message in chat.db on startup."""
    msgs = await imsg.list_recent_inbound(since_rowid=0, limit=10000)
    if not msgs:
        return -1
    max_rowid = max(m.rowid for m in msgs)
    await _set_watermark(max_rowid)
    log.info("imessage listener bootstrapped watermark", rowid=max_rowid)
    return max_rowid


async def _maybe_reply(msg: imsg.InboundMessage) -> Optional[str]:
    """if the inbound text mentions ro, dispatch to the comms agent to draft
    a reply. returns the opened action_id, if any."""
    if not MENTION_RE.search(msg.text):
        return None
    try:
        from api.agents.comms.agent import comms_agent

        # phrase the request as ro would have heard it
        instruction = (
            f"{msg.chat_display} just texted me on imessage: \"{msg.text}\"\n\n"
            f"draft a reply via imessage to {msg.from_handle or msg.chat_display}."
        )
        result = await comms_agent.run(
            session_id=str(uuid.uuid4()),
            user_text=instruction,
            context={},
        )
        if result.actions_opened:
            return str(result.actions_opened[0])
    except Exception:
        log.exception("imessage mention dispatch failed", rowid=msg.rowid)
    return None


async def run_once() -> dict[str, int]:
    """one poll iteration. returns counts for logging."""
    if not imsg.configured():
        return {"skipped": 1}

    watermark = await _get_watermark()
    if watermark < 0:
        watermark = await _bootstrap_watermark()
        return {"bootstrapped": 1}

    msgs = await imsg.list_recent_inbound(since_rowid=watermark, limit=50)
    if not msgs:
        return {"new": 0}

    new = 0
    replies = 0
    highest = watermark
    for m in msgs:
        new += 1
        highest = max(highest, m.rowid)

        # capture into memory tree
        try:
            await tree_write(
                source="imessage",
                kind="received",
                actor="external",
                summary=f"iMessage from {m.chat_display}: {m.text[:160]}",
                payload={
                    "rowid": m.rowid, "from": m.from_handle,
                    "chat": m.chat_display, "text": m.text[:1500],
                },
            )
        except Exception:
            log.warning("imessage tree write failed", rowid=m.rowid)

        # if it mentions ro, dispatch
        action_id = await _maybe_reply(m)
        if action_id:
            replies += 1
            log.info("imessage mention triggered reply draft", rowid=m.rowid, action_id=action_id)

    await _set_watermark(highest)
    return {"new": new, "replies_drafted": replies, "watermark": highest}


async def loop() -> None:
    """background task entry. uses bootstrap + poll loop."""
    # let the api come up
    await asyncio.sleep(8)

    if not imsg.configured():
        log.warning("imessage listener disabled — chat.db not readable (grant Full Disk Access)")
        return

    log.info("imessage listener started", poll_s=POLL_INTERVAL_S)
    while True:
        try:
            counts = await run_once()
            if counts.get("new"):
                log.info("imessage listener tick", **counts)
        except Exception:
            log.exception("imessage listener iteration failed")
        await asyncio.sleep(POLL_INTERVAL_S)
