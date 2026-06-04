"""slack client.

uses a user token (xoxp-…) or bot token (xoxb-…) from keychain `slack_token`.
user tokens give you access to DMs as yourself (which is what ro needs).

verbs:
- configured()
- list_channels(types='public_channel,private_channel,im,mpim', limit=200) -> list[Channel]
- search_messages(query, count=10)                                          -> list[SearchHit]
- list_recent_dms(limit=10)                                                 -> list[Channel]
- fetch_history(channel_id, limit=20)                                       -> list[Message]
- find_user_by_name(name)                                                   -> User | None
- post_message(channel_id, text, thread_ts=None)                            -> dict
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

from slack_sdk.web.async_client import AsyncWebClient

from api.config import secrets
from api.observability.logging import log


@dataclass
class Channel:
    channel_id: str
    name: str          # channel name or DM user display
    is_dm: bool
    is_private: bool
    user_id: str = ""  # set when is_dm=True
    last_active: str = ""


@dataclass
class Message:
    ts: str
    user_id: str
    user_name: str
    text: str
    channel_id: str
    thread_ts: str = ""


@dataclass
class SearchHit:
    ts: str
    channel_id: str
    channel_name: str
    user_id: str
    user_name: str
    text: str
    permalink: str = ""


@dataclass
class User:
    user_id: str
    name: str
    real_name: str
    is_bot: bool = False


def configured() -> bool:
    return bool(secrets.get("slack_token"))


def _client() -> AsyncWebClient:
    token = secrets.get("slack_token")
    if not token:
        raise RuntimeError(
            "slack not configured. run `keyring set ro slack_token` with a user "
            "token (xoxp-…) — get one from https://api.slack.com/apps"
        )
    return AsyncWebClient(token=token)


# ----- channels / dms -----


async def list_channels(types: str = "public_channel,private_channel,im,mpim", limit: int = 200) -> list[Channel]:
    c = _client()
    try:
        resp = await c.conversations_list(types=types, limit=limit, exclude_archived=True)
    except Exception as e:
        log.warning("slack list_channels failed", error=str(e))
        return []
    chans = resp.data.get("channels", [])
    out: list[Channel] = []
    user_cache: dict[str, str] = {}
    for ch in chans:
        is_dm = ch.get("is_im", False)
        if is_dm:
            uid = ch.get("user", "")
            if uid and uid not in user_cache:
                try:
                    info = await c.users_info(user=uid)
                    user_cache[uid] = info.data.get("user", {}).get("real_name") or info.data.get("user", {}).get("name", uid)
                except Exception:
                    user_cache[uid] = uid
            out.append(Channel(
                channel_id=ch["id"],
                name=user_cache.get(uid, uid),
                is_dm=True,
                is_private=True,
                user_id=uid,
            ))
        else:
            out.append(Channel(
                channel_id=ch["id"],
                name=ch.get("name", "(unnamed)"),
                is_dm=False,
                is_private=ch.get("is_private", False),
            ))
    return out


async def list_recent_dms(limit: int = 10) -> list[Channel]:
    """list dms ordered by most recent message."""
    c = _client()
    try:
        resp = await c.conversations_list(types="im", limit=200, exclude_archived=True)
    except Exception as e:
        log.warning("slack list_recent_dms failed", error=str(e))
        return []
    ims = resp.data.get("channels", [])

    # sort by latest activity if available, else as returned
    ims = sorted(ims, key=lambda x: float(x.get("updated", 0)), reverse=True)
    out: list[Channel] = []
    for ch in ims[:limit]:
        uid = ch.get("user", "")
        try:
            info = await c.users_info(user=uid)
            name = info.data.get("user", {}).get("real_name") or info.data.get("user", {}).get("name", uid)
        except Exception:
            name = uid
        out.append(Channel(
            channel_id=ch["id"],
            name=name,
            is_dm=True,
            is_private=True,
            user_id=uid,
        ))
    return out


# ----- search / history -----


async def search_messages(query: str, count: int = 10) -> list[SearchHit]:
    """requires search:read; not available on bot tokens."""
    c = _client()
    try:
        resp = await c.search_messages(query=query, count=count)
    except Exception as e:
        log.warning("slack search_messages failed", error=str(e))
        return []
    matches = resp.data.get("messages", {}).get("matches", [])
    out: list[SearchHit] = []
    for m in matches:
        out.append(SearchHit(
            ts=m.get("ts", ""),
            channel_id=m.get("channel", {}).get("id", ""),
            channel_name=m.get("channel", {}).get("name", ""),
            user_id=m.get("user", ""),
            user_name=m.get("username", ""),
            text=m.get("text", ""),
            permalink=m.get("permalink", ""),
        ))
    return out


async def fetch_history(channel_id: str, limit: int = 20) -> list[Message]:
    c = _client()
    try:
        resp = await c.conversations_history(channel=channel_id, limit=limit)
    except Exception as e:
        log.warning("slack fetch_history failed", channel=channel_id, error=str(e))
        return []
    msgs = resp.data.get("messages", [])
    user_cache: dict[str, str] = {}
    out: list[Message] = []
    for m in msgs:
        uid = m.get("user", "")
        if uid and uid not in user_cache:
            try:
                info = await c.users_info(user=uid)
                user_cache[uid] = info.data.get("user", {}).get("real_name") or info.data.get("user", {}).get("name", uid)
            except Exception:
                user_cache[uid] = uid
        out.append(Message(
            ts=m.get("ts", ""),
            user_id=uid,
            user_name=user_cache.get(uid, ""),
            text=m.get("text", ""),
            channel_id=channel_id,
            thread_ts=m.get("thread_ts", ""),
        ))
    return out


# ----- users -----


async def find_user_by_name(name: str) -> Optional[User]:
    """fuzzy find a user by display/real name."""
    if not name:
        return None
    c = _client()
    name_low = name.lower()
    cursor: Optional[str] = None
    while True:
        try:
            resp = await c.users_list(cursor=cursor, limit=200)
        except Exception as e:
            log.warning("slack users_list failed", error=str(e))
            return None
        for u in resp.data.get("members", []):
            if u.get("deleted") or u.get("is_bot") and "bot" not in name_low:
                continue
            real = (u.get("real_name") or "").lower()
            disp = (u.get("profile", {}).get("display_name") or "").lower()
            handle = (u.get("name") or "").lower()
            if name_low in real or name_low in disp or name_low in handle:
                return User(
                    user_id=u["id"],
                    name=u.get("name", ""),
                    real_name=u.get("real_name", ""),
                    is_bot=u.get("is_bot", False),
                )
        cursor = (resp.data.get("response_metadata") or {}).get("next_cursor", "")
        if not cursor:
            return None


async def open_dm(user_id: str) -> str:
    """open (or fetch) a dm channel with a user; returns channel id."""
    c = _client()
    resp = await c.conversations_open(users=user_id)
    return resp.data.get("channel", {}).get("id", "")


# ----- send -----


async def post_message(channel_id: str, text: str, thread_ts: Optional[str] = None) -> dict[str, Any]:
    c = _client()
    kwargs: dict[str, Any] = {"channel": channel_id, "text": text}
    if thread_ts:
        kwargs["thread_ts"] = thread_ts
    resp = await c.chat_postMessage(**kwargs)
    return {"ts": resp.data.get("ts", ""), "channel": resp.data.get("channel", "")}
