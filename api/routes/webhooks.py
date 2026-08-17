"""inbound webhooks. so far: twilio whatsapp.

twilio POSTs form-encoded data. validates X-Twilio-Signature using the auth token
already stored in keychain — if validation fails the request is 403'd.
"""

from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from api.integrations import whatsapp as wa
from api.memory.tree import write_event as tree_write
from api.observability.logging import log

router = APIRouter()

MENTION_RE = re.compile(
    r"(?:(?:\bhey\s+ro\b)|(?:@ro\b)|(?:^\s*ro[\s,:!?-]))",
    re.IGNORECASE,
)


@router.post("/webhooks/whatsapp", response_class=PlainTextResponse)
async def whatsapp_inbound(request: Request) -> str:
    """twilio whatsapp messaging webhook.

    on inbound message:
      1. validate signature
      2. write to memory tree (gmail/imessage/telegram parity)
      3. if the user txt mentions ro, dispatch the comms agent to draft a reply
    twilio expects a TwiML response; an empty 200 is fine for "no reply now".
    """
    form_raw = await request.form()
    form = {k: str(v) for k, v in form_raw.items()}

    sig = request.headers.get("x-twilio-signature", "")
    # rebuild the externally-visible URL twilio used. honor an X-Forwarded-Proto/Host
    # set by the reverse proxy / tailscale-serve, else fall back to request.url.
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    full_url = f"{proto}://{host}{request.url.path}"

    if not wa.validate_signature(url=full_url, form=form, signature=sig):
        log.warning("whatsapp webhook signature mismatch",
                    url=full_url, has_sig=bool(sig))
        raise HTTPException(403, "invalid twilio signature")

    body = (form.get("Body") or "").strip()
    sender = (form.get("From") or "").replace("whatsapp:", "")
    profile_name = form.get("ProfileName") or ""
    msg_sid = form.get("MessageSid") or ""

    if not body:
        return ""

    # 1. tree event
    try:
        await tree_write(
            source="whatsapp",
            kind="received",
            actor="external",
            summary=f"whatsapp from {profile_name or sender}: {body[:160]}",
            payload={"from": sender, "name": profile_name,
                     "sid": msg_sid, "text": body[:1500]},
        )
    except Exception:
        log.warning("whatsapp tree write failed", sid=msg_sid)

    # 2. mention → draft a reply
    if MENTION_RE.search(body):
        try:
            from api.listeners import gateway

            instruction = (
                f"{profile_name or sender} just whatsapped me: \"{body}\"\n\n"
                f"draft a reply via whatsapp to {sender}."
            )
            await gateway.handle_inbound(
                channel="whatsapp", chat_key=sender, text=instruction, reply=None,
            )
        except Exception:
            log.exception("whatsapp dispatch failed", sid=msg_sid)

    return ""  # 200 with empty body = no inline reply; we use approval cards in the chat
