"""imessage client.

reads from ~/Library/Messages/chat.db (read-only, requires Full Disk Access for
the running terminal/python). sends via AppleScript through `osascript`.

verbs:
- configured()                                      -> bool (chat.db readable?)
- list_recent_threads(limit=10)                     -> list[Thread]
- search_messages(query, limit=20)                  -> list[Message]
- recent_with(name_or_handle, limit=20)             -> list[Message]
- send_message(handle, text)                        -> bool
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from api.observability.logging import log

CHAT_DB = Path.home() / "Library" / "Messages" / "chat.db"
# imessage stores ts as nanoseconds since 2001-01-01 utc
APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)


@dataclass
class Thread:
    chat_id: int
    display_name: str
    handles: list[str] = field(default_factory=list)
    last_text: str = ""
    last_at: str = ""
    last_from_me: bool = False


@dataclass
class Message:
    text: str
    from_handle: str
    from_me: bool
    sent_at: str
    chat_id: int = 0


@dataclass
class InboundMessage:
    """one new inbound message picked up by the listener."""
    rowid: int          # chat.db message.rowid (stable, monotonic)
    text: str
    from_handle: str
    chat_id: int
    chat_display: str
    sent_at: str


def configured() -> bool:
    """chat.db has to exist AND be readable (full disk access on macos)."""
    if not CHAT_DB.exists():
        return False
    try:
        with sqlite3.connect(f"file:{CHAT_DB}?mode=ro", uri=True) as c:
            c.execute("select 1 from message limit 1").fetchone()
        return True
    except sqlite3.OperationalError:
        return False
    except Exception:
        return False


# ----- read -----


def _connect():
    return sqlite3.connect(f"file:{CHAT_DB}?mode=ro&immutable=1", uri=True)


def _to_iso(apple_ns: Optional[int]) -> str:
    if not apple_ns:
        return ""
    try:
        # newer macos stores nanoseconds; older stores seconds. detect by magnitude.
        if apple_ns > 10**13:
            secs = apple_ns / 1e9
        else:
            secs = float(apple_ns)
        dt = APPLE_EPOCH.fromtimestamp(secs + APPLE_EPOCH.timestamp(), tz=timezone.utc)
        return dt.isoformat()
    except Exception:
        return ""


async def list_recent_threads(limit: int = 10) -> list[Thread]:
    return await asyncio.to_thread(_list_recent_threads, limit)


def _list_recent_threads(limit: int) -> list[Thread]:
    with _connect() as c:
        rows = c.execute(
            """
            with last_msg as (
                select cmj.chat_id, max(m.date) as last_date
                from chat_message_join cmj
                join message m on m.rowid = cmj.message_id
                group by cmj.chat_id
            )
            select c.rowid, c.display_name, c.chat_identifier,
                   m.text, m.date, m.is_from_me
            from chat c
            join last_msg lm on lm.chat_id = c.rowid
            join chat_message_join cmj on cmj.chat_id = c.rowid
            join message m on m.rowid = cmj.message_id and m.date = lm.last_date
            order by m.date desc
            limit ?
            """,
            (limit,),
        ).fetchall()

        out: list[Thread] = []
        for chat_id, display_name, identifier, text, date, is_from_me in rows:
            # collect handles for this chat
            handle_rows = c.execute(
                """select h.id from chat_handle_join chj
                   join handle h on h.rowid = chj.handle_id
                   where chj.chat_id = ?""",
                (chat_id,),
            ).fetchall()
            handles = [h[0] for h in handle_rows if h[0]]
            out.append(Thread(
                chat_id=chat_id,
                display_name=(display_name or "").strip() or (handles[0] if handles else identifier),
                handles=handles,
                last_text=(text or "").strip(),
                last_at=_to_iso(date),
                last_from_me=bool(is_from_me),
            ))
        return out


async def search_messages(query: str, limit: int = 20) -> list[Message]:
    return await asyncio.to_thread(_search_messages, query, limit)


def _search_messages(query: str, limit: int) -> list[Message]:
    if not query.strip():
        return []
    with _connect() as c:
        rows = c.execute(
            """
            select m.text, m.is_from_me, m.date, h.id, cmj.chat_id
            from message m
            left join handle h on h.rowid = m.handle_id
            left join chat_message_join cmj on cmj.message_id = m.rowid
            where m.text like ?
            order by m.date desc
            limit ?
            """,
            (f"%{query}%", limit),
        ).fetchall()
        return [
            Message(
                text=(text or "").strip(),
                from_handle=(handle or ""),
                from_me=bool(is_from_me),
                sent_at=_to_iso(date),
                chat_id=chat_id or 0,
            )
            for text, is_from_me, date, handle, chat_id in rows
        ]


async def list_recent_inbound(since_rowid: int = 0, limit: int = 50) -> list[InboundMessage]:
    """fetch inbound messages with rowid > `since_rowid`. used by the listener."""
    return await asyncio.to_thread(_list_recent_inbound, since_rowid, limit)


def _list_recent_inbound(since_rowid: int, limit: int) -> list[InboundMessage]:
    with _connect() as c:
        rows = c.execute(
            """
            select m.rowid, m.text, h.id, m.date, cmj.chat_id, c.display_name, c.chat_identifier
            from message m
            left join handle h on h.rowid = m.handle_id
            left join chat_message_join cmj on cmj.message_id = m.rowid
            left join chat c on c.rowid = cmj.chat_id
            where m.is_from_me = 0
              and m.rowid > ?
              and m.text is not null
              and length(trim(m.text)) > 0
            order by m.rowid asc
            limit ?
            """,
            (since_rowid, limit),
        ).fetchall()
        out: list[InboundMessage] = []
        for rowid, text, handle, date, chat_id, display, ident in rows:
            display = (display or "").strip() or (handle or ident or "(unknown)")
            out.append(InboundMessage(
                rowid=int(rowid),
                text=(text or "").strip(),
                from_handle=(handle or "") or (ident or ""),
                chat_id=int(chat_id or 0),
                chat_display=display,
                sent_at=_to_iso(date),
            ))
        return out


async def channel_messages(channel_key: str, since_rowid: int = 0, limit: int = 50) -> list[InboundMessage]:
    """all new messages in the ro channel, regardless of is_from_me.

    the ro channel is matched by chat_identifier, display name, or member
    handle. in the self chat every row reads as sent (same apple id from
    phone and mac), so the caller separates ro's own replies via the
    gateway's sent-text tracking, not this query.
    """
    return await asyncio.to_thread(_channel_messages, channel_key, since_rowid, limit)


def _channel_messages(channel_key: str, since_rowid: int, limit: int) -> list[InboundMessage]:
    needle = channel_key.strip().lower()
    if not needle:
        return []
    with _connect() as c:
        rows = c.execute(
            """
            select m.rowid, m.text, m.date, h.id, cmj.chat_id,
                   coalesce(c2.display_name, ''), coalesce(c2.chat_identifier, '')
            from message m
            left join handle h on h.rowid = m.handle_id
            join chat_message_join cmj on cmj.message_id = m.rowid
            join chat c2 on c2.rowid = cmj.chat_id
            where m.rowid > ?
              and coalesce(m.text, '') != ''
              and (
                lower(coalesce(c2.chat_identifier, '')) like ?
                or lower(coalesce(c2.display_name, '')) like ?
                or cmj.chat_id in (
                    select chj.chat_id from chat_handle_join chj
                    join handle h2 on h2.rowid = chj.handle_id
                    where lower(coalesce(h2.id, '')) like ?
                )
              )
            order by m.rowid asc
            limit ?
            """,
            (since_rowid, f"%{needle}%", f"%{needle}%", f"%{needle}%", limit),
        ).fetchall()
        return [
            InboundMessage(
                rowid=int(rowid),
                text=(text or "").strip(),
                from_handle=(handle or "") or (ident or ""),
                chat_id=int(chat_id or 0),
                chat_display=(display or "").strip() or (ident or "(ro channel)"),
                sent_at=_to_iso(date),
            )
            for rowid, text, date, handle, chat_id, display, ident in rows
        ]


async def recent_with(name_or_handle: str, limit: int = 20) -> list[Message]:
    return await asyncio.to_thread(_recent_with, name_or_handle, limit)


def _recent_with(name_or_handle: str, limit: int) -> list[Message]:
    if not name_or_handle.strip():
        return []
    needle = name_or_handle.strip().lower()
    with _connect() as c:
        # find candidate chats by display_name OR handle id match
        chat_rows = c.execute(
            """
            select distinct c.rowid
            from chat c
            left join chat_handle_join chj on chj.chat_id = c.rowid
            left join handle h on h.rowid = chj.handle_id
            where lower(coalesce(c.display_name,'')) like ?
               or lower(coalesce(h.id,'')) like ?
            """,
            (f"%{needle}%", f"%{needle}%"),
        ).fetchall()
        chat_ids = [r[0] for r in chat_rows]
        if not chat_ids:
            return []
        qmarks = ",".join("?" for _ in chat_ids)
        rows = c.execute(
            f"""
            select m.text, m.is_from_me, m.date, h.id, cmj.chat_id
            from message m
            left join handle h on h.rowid = m.handle_id
            join chat_message_join cmj on cmj.message_id = m.rowid
            where cmj.chat_id in ({qmarks})
            order by m.date desc
            limit ?
            """,
            (*chat_ids, limit),
        ).fetchall()
        return [
            Message(
                text=(text or "").strip(),
                from_handle=(handle or ""),
                from_me=bool(is_from_me),
                sent_at=_to_iso(date),
                chat_id=chat_id or 0,
            )
            for text, is_from_me, date, handle, chat_id in rows
        ]


# ----- send (applescript) -----


async def send_message(handle: str, text: str) -> bool:
    """send via osascript. handle = phone number or email registered with iMessage."""
    return await asyncio.to_thread(_send_message, handle, text)


# handle and text arrive as argv, never interpolated into the script source.
# a quote-bearing handle or body cannot break out into arbitrary applescript.
_SEND_SCRIPT = '''
on run argv
    set theHandle to item 1 of argv
    set theText to item 2 of argv
    tell application "Messages"
        set targetService to 1st service whose service type = iMessage
        set targetBuddy to buddy theHandle of targetService
        send theText to targetBuddy
    end tell
end run
'''


def _send_message(handle: str, text: str) -> bool:
    import subprocess
    try:
        r = subprocess.run(
            ["osascript", "-e", _SEND_SCRIPT, handle, text],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode != 0:
            log.warning("imessage send failed", stderr=r.stderr.strip())
            return False
        return True
    except Exception:
        log.exception("imessage send error")
        return False
