"""gmail client.

uses google-api-python-client with oauth user credentials stored at
~/.config/ro/gmail_token.json. one-time setup writes the token via
scripts/setup_gmail_oauth.py.

api surface (async wrappers; the underlying client is sync, so we run it on a
thread executor):

- configured()                                 -> bool
- search_threads(query, max=10)                -> list[ThreadSummary]
- get_thread(thread_id)                        -> Thread
- create_draft(to, subject, body, reply_to_thread_id?)
                                              -> Draft
- send_draft(draft_id)                         -> SentMessage
- send_message(to, subject, body, thread_id?)  -> SentMessage  (no draft, direct)
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Any, Optional

from api.integrations import google_auth
from api.observability.logging import log


@dataclass
class ThreadSummary:
    thread_id: str
    from_name: str
    from_email: str
    subject: str
    snippet: str
    received_at: str
    unread: bool
    labels: list[str] = field(default_factory=list)


@dataclass
class Message:
    message_id: str
    thread_id: str
    from_name: str
    from_email: str
    to: list[str]
    subject: str
    body: str
    received_at: str


@dataclass
class Thread:
    thread_id: str
    subject: str
    messages: list[Message]


@dataclass
class Draft:
    draft_id: str
    message_id: str
    to: str
    subject: str
    body: str
    thread_id: Optional[str] = None


@dataclass
class SentMessage:
    message_id: str
    thread_id: str


def configured() -> bool:
    return google_auth.configured()


def _service():
    return google_auth.service("gmail", "v1")


async def _run(fn, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))


# ----- public verbs -----


async def search_threads(query: str = "", max_results: int = 10) -> list[ThreadSummary]:
    if not configured():
        return []
    svc = _service()

    def _do():
        resp = (
            svc.users()
            .threads()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
        items = resp.get("threads", [])
        out: list[ThreadSummary] = []
        for it in items:
            tid = it["id"]
            t = svc.users().threads().get(userId="me", id=tid, format="metadata",
                                          metadataHeaders=["From", "Subject", "Date"]).execute()
            msgs = t.get("messages", [])
            if not msgs:
                continue
            last = msgs[-1]
            headers = {h["name"].lower(): h["value"] for h in last.get("payload", {}).get("headers", [])}
            from_raw = headers.get("from", "")
            from_name, from_email = _parse_addr(from_raw)
            out.append(
                ThreadSummary(
                    thread_id=tid,
                    from_name=from_name,
                    from_email=from_email,
                    subject=headers.get("subject", "(no subject)"),
                    snippet=last.get("snippet", ""),
                    received_at=headers.get("date", ""),
                    unread="UNREAD" in last.get("labelIds", []),
                    labels=last.get("labelIds", []),
                )
            )
        return out

    return await _run(_do)


async def get_thread(thread_id: str) -> Thread:
    svc = _service()

    def _do():
        t = svc.users().threads().get(userId="me", id=thread_id, format="full").execute()
        msgs = []
        for m in t.get("messages", []):
            payload = m.get("payload", {})
            headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
            from_raw = headers.get("from", "")
            from_name, from_email = _parse_addr(from_raw)
            body = _extract_body(payload)
            msgs.append(
                Message(
                    message_id=m["id"],
                    thread_id=thread_id,
                    from_name=from_name,
                    from_email=from_email,
                    to=[a.strip() for a in headers.get("to", "").split(",") if a.strip()],
                    subject=headers.get("subject", "(no subject)"),
                    body=body,
                    received_at=headers.get("date", ""),
                )
            )
        return Thread(
            thread_id=thread_id,
            subject=msgs[0].subject if msgs else "(no subject)",
            messages=msgs,
        )

    return await _run(_do)


async def create_draft(
    *,
    to: str,
    subject: str,
    body: str,
    reply_to_thread_id: Optional[str] = None,
    in_reply_to_message_id: Optional[str] = None,
) -> Draft:
    svc = _service()

    def _do():
        msg = EmailMessage()
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        if in_reply_to_message_id:
            msg["In-Reply-To"] = in_reply_to_message_id
            msg["References"] = in_reply_to_message_id

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        draft_body: dict[str, Any] = {"message": {"raw": raw}}
        if reply_to_thread_id:
            draft_body["message"]["threadId"] = reply_to_thread_id

        d = svc.users().drafts().create(userId="me", body=draft_body).execute()
        return Draft(
            draft_id=d["id"],
            message_id=d["message"]["id"],
            to=to,
            subject=subject,
            body=body,
            thread_id=reply_to_thread_id,
        )

    return await _run(_do)


async def send_draft(draft_id: str) -> SentMessage:
    svc = _service()

    def _do():
        sent = svc.users().drafts().send(userId="me", body={"id": draft_id}).execute()
        return SentMessage(message_id=sent["id"], thread_id=sent.get("threadId", ""))

    return await _run(_do)


async def send_message(
    *,
    to: str,
    subject: str,
    body: str,
    thread_id: Optional[str] = None,
) -> SentMessage:
    svc = _service()

    def _do():
        msg = EmailMessage()
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        send_body: dict[str, Any] = {"raw": raw}
        if thread_id:
            send_body["threadId"] = thread_id
        sent = svc.users().messages().send(userId="me", body=send_body).execute()
        return SentMessage(message_id=sent["id"], thread_id=sent.get("threadId", ""))

    return await _run(_do)


# ----- helpers -----


def _parse_addr(raw: str) -> tuple[str, str]:
    """parse 'Name <email@host>' into (name, email)."""
    raw = raw.strip()
    if not raw:
        return ("", "")
    if "<" in raw and ">" in raw:
        name = raw.split("<")[0].strip().strip('"')
        email = raw.split("<")[1].split(">")[0].strip()
        return (name or email.split("@")[0], email)
    return (raw.split("@")[0], raw)


def _decode_part(part: dict[str, Any]) -> str:
    data = part.get("body", {}).get("data")
    if not data:
        return ""
    return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")


def _walk_parts(payload: dict[str, Any], mime: str) -> str:
    """depth-first search for the first part of the given mime type.
    multipart/alternative nested inside multipart/mixed is the common case
    a single-level scan misses."""
    if payload.get("mimeType") == mime:
        text = _decode_part(payload)
        if text:
            return text
    for part in payload.get("parts", []) or []:
        found = _walk_parts(part, mime)
        if found:
            return found
    return ""


def _extract_body(payload: dict[str, Any]) -> str:
    """find the text/plain body anywhere in the part tree, html fallback."""
    text = _walk_parts(payload, "text/plain")
    if text:
        return text
    html = _walk_parts(payload, "text/html")
    if html:
        return _strip_html(html)
    return ""


def _strip_html(html: str) -> str:
    import re
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text
