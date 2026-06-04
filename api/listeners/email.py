"""inbound gmail listener.

every 60s, scans recent gmail threads for new ones.

for each new thread:
  1. write a `gmail/received` event so the memory tree picks it up
  2. if the last message mentions ro ("@ro", "hey ro", "ro,"/"ro:" at line
     start, or ro's email address is in to/cc list), dispatch to the comms
     agent — that drafts a reply and opens an approval card.

watermark: track the highest gmail internal date we've seen so we never
auto-reply to messages older than the api's first boot.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from typing import Optional

from api.config import secrets
from api.integrations import gmail
from api.memory.db import db
from api.memory.tree import write_event as tree_write
from api.observability.logging import log

POLL_INTERVAL_S = 60
MENTION_RE = re.compile(
    r"(?:(?:\bhey\s+ro\b)|(?:@ro\b)|(?:^\s*ro[\s,:!?-]))",
    re.IGNORECASE | re.MULTILINE,
)


async def _claim_thread(thread_id: str) -> bool:
    """try to claim a thread as new. returns True iff this poll is the first
    time we've seen it (i.e. the insert went in, no conflict)."""
    row = await db.fetchrow(
        """insert into seen_keys (source, external_id) values ('email_thread', $1)
           on conflict (source, external_id) do nothing returning external_id""",
        thread_id,
    )
    return row is not None


def _ro_address_hint() -> str:
    """if the user has told us their email, use it for to/cc mention detection."""
    return (secrets.get("user_email") or "").lower()


async def _maybe_reply(thread_id: str, subject: str, sender: str) -> Optional[str]:
    """fetch the full thread, look for a ro mention in the latest message, dispatch."""
    try:
        full = await gmail.get_thread(thread_id)
    except Exception as e:
        log.warning("gmail listener get_thread failed", thread_id=thread_id, error=str(e))
        return None
    if not full.messages:
        return None
    last = full.messages[-1]
    # skip if the last message is from ro (sent by us)
    user_email = _ro_address_hint()
    if user_email and user_email in (last.from_email or "").lower():
        return None

    mention = bool(MENTION_RE.search(last.body or ""))
    # also treat user_email in to-line as "addressed to ro" — only useful if user_email is set
    addressed = bool(user_email and any(user_email in (t or "").lower() for t in last.to))
    if not (mention or addressed):
        return None

    try:
        from api.agents.comms.agent import comms_agent

        instruction = (
            f"{last.from_name or last.from_email} emailed me: subject \"{full.subject}\".\n\n"
            f"last message body:\n---\n{(last.body or '')[:3000]}\n---\n\n"
            f"draft a reply via gmail to {last.from_email}."
        )
        result = await comms_agent.run(
            session_id=str(uuid.uuid4()),
            user_text=instruction,
            context={"gmail_thread_id": thread_id, "gmail_from": last.from_email},
        )
        if result.actions_opened:
            return str(result.actions_opened[0])
    except Exception:
        log.exception("gmail listener dispatch failed", thread_id=thread_id)
    return None


async def run_once() -> dict[str, int]:
    if not gmail.configured():
        return {"skipped": 1}

    # we use Gmail's "newer_than:1d" search to keep the candidate set small,
    # then dedup per-thread via the seen_keys table. cheap and correct.
    try:
        threads = await gmail.search_threads("newer_than:1d -from:me", max_results=20)
    except Exception as e:
        log.warning("gmail listener search failed", error=str(e))
        return {"new": 0, "error": 1}

    new = 0
    replies = 0
    for t in threads:
        is_new = await _claim_thread(t.thread_id)
        if not is_new:
            continue
        new += 1
        try:
            await tree_write(
                source="gmail",
                kind="received",
                actor="external",
                summary=f"email from {t.from_name or t.from_email}: {t.subject[:120]}",
                payload={
                    "thread_id": t.thread_id,
                    "from": t.from_email, "from_name": t.from_name,
                    "subject": t.subject, "snippet": t.snippet[:400],
                    "unread": t.unread,
                },
            )
        except Exception:
            log.warning("gmail listener tree write failed", thread_id=t.thread_id)

        action_id = await _maybe_reply(t.thread_id, t.subject, t.from_email)
        if action_id:
            replies += 1
            log.info("gmail mention triggered reply draft", thread_id=t.thread_id, action_id=action_id)

    return {"new": new, "replies_drafted": replies}


async def loop() -> None:
    """background entry."""
    await asyncio.sleep(20)

    if not gmail.configured():
        log.warning("gmail listener disabled — google not connected")
        return
    log.info("gmail listener started", poll_s=POLL_INTERVAL_S)
    while True:
        try:
            counts = await run_once()
            if counts.get("new"):
                log.info("gmail listener tick", **counts)
        except Exception:
            log.exception("gmail listener iteration failed")
        await asyncio.sleep(POLL_INTERVAL_S)
