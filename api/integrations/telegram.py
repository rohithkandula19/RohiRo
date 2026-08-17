"""telegram client.

uses a bot token from BotFather, stored in keychain as `telegram_bot_token`.
optionally restricts inbound to `telegram_owner_id` (your chat id with the bot)
so strangers messaging the bot are ignored.

verbs:
- configured()
- get_updates(offset=None, timeout=0)              -> list[Update]   (long-poll capable)
- send_message(chat_id, text)                       -> dict
- get_me()                                          -> dict (bot identity)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import httpx

from api.config import secrets
from api.observability.logging import log

_API = "https://api.telegram.org/bot"


@dataclass
class TGUpdate:
    update_id: int
    chat_id: int
    chat_kind: str     # private | group | supergroup | channel
    chat_title: str    # group name or sender's first name for DMs
    from_id: int
    from_name: str
    text: str
    date: str          # iso utc
    # callback_query fields (button presses). text stays "" for callbacks.
    callback_id: str = ""
    callback_data: str = ""
    message_id: int = 0


def configured() -> bool:
    return bool(secrets.get("telegram_bot_token"))


def _base() -> str:
    token = secrets.get("telegram_bot_token")
    if not token:
        raise RuntimeError(
            "telegram not configured. talk to @BotFather, get a token, then "
            "`keyring set ro telegram_bot_token`. for owner-restricted mode also "
            "`keyring set ro telegram_owner_id` with your numeric chat id."
        )
    return f"{_API}{token}"


def owner_id() -> Optional[int]:
    v = secrets.get("telegram_owner_id")
    if not v:
        return None
    try:
        return int(v)
    except ValueError:
        return None


async def get_me() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.get(f"{_base()}/getMe")
        r.raise_for_status()
        return r.json().get("result") or {}


async def get_updates(offset: Optional[int] = None, *, timeout: int = 0, limit: int = 50) -> list[TGUpdate]:
    params: dict[str, Any] = {"limit": limit, "timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    async with httpx.AsyncClient(timeout=max(20.0, timeout + 5.0)) as c:
        try:
            r = await c.get(f"{_base()}/getUpdates", params=params)
        except Exception as e:
            log.warning("telegram getUpdates failed", error=str(e))
            return []
        if r.status_code != 200:
            log.warning("telegram getUpdates non-200", status=r.status_code, body=r.text[:200])
            return []
        items = r.json().get("result") or []
        out: list[TGUpdate] = []
        for u in items:
            cb = u.get("callback_query")
            if cb:
                cb_msg = cb.get("message") or {}
                cb_chat = cb_msg.get("chat") or {}
                cb_frm = cb.get("from") or {}
                out.append(TGUpdate(
                    update_id=u.get("update_id", 0),
                    chat_id=cb_chat.get("id", 0),
                    chat_kind=cb_chat.get("type", "private"),
                    chat_title=(cb_chat.get("title") or cb_chat.get("first_name") or "").strip() or str(cb_chat.get("id", "?")),
                    from_id=cb_frm.get("id", 0),
                    from_name=(cb_frm.get("first_name") or ""),
                    text="",
                    date=_iso(cb_msg.get("date")),
                    callback_id=str(cb.get("id") or ""),
                    callback_data=str(cb.get("data") or ""),
                    message_id=cb_msg.get("message_id", 0),
                ))
                continue
            msg = u.get("message") or u.get("edited_message") or u.get("channel_post")
            if not msg:
                continue
            text = (msg.get("text") or "").strip()
            if not text:
                continue
            chat = msg.get("chat") or {}
            frm = msg.get("from") or {}
            out.append(TGUpdate(
                update_id=u.get("update_id", 0),
                chat_id=chat.get("id", 0),
                chat_kind=chat.get("type", "private"),
                chat_title=(chat.get("title") or chat.get("first_name") or "").strip() or str(chat.get("id", "?")),
                from_id=frm.get("id", 0),
                from_name=(frm.get("first_name") or "") + ((" " + frm.get("last_name")) if frm.get("last_name") else ""),
                text=text,
                date=_iso(msg.get("date")),
            ))
        return out


async def answer_callback(callback_id: str, text: str = "") -> None:
    """ack a button press so the client stops its spinner. best effort."""
    async with httpx.AsyncClient(timeout=10.0) as c:
        try:
            await c.post(f"{_base()}/answerCallbackQuery",
                         json={"callback_query_id": callback_id, "text": text[:180]})
        except Exception:
            log.warning("telegram answerCallbackQuery failed")


async def edit_message(chat_id: int, message_id: int, text: str) -> None:
    """rewrite a sent message (used to show an approval's outcome). best effort."""
    async with httpx.AsyncClient(timeout=10.0) as c:
        try:
            await c.post(f"{_base()}/editMessageText",
                         json={"chat_id": chat_id, "message_id": message_id, "text": text[:4000]})
        except Exception:
            log.warning("telegram editMessageText failed")


async def send_message(
    chat_id: int,
    text: str,
    *,
    parse_mode: Optional[str] = None,
    reply_markup: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"chat_id": chat_id, "text": text}
    if parse_mode:
        body["parse_mode"] = parse_mode
    if reply_markup:
        body["reply_markup"] = reply_markup
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.post(f"{_base()}/sendMessage", json=body)
        if r.status_code != 200:
            raise RuntimeError(f"telegram send failed: {r.status_code} {r.text[:300]}")
        return r.json().get("result") or {}


def _iso(ts: Any) -> str:
    if not ts:
        return ""
    try:
        from datetime import datetime, timezone
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except Exception:
        return ""
