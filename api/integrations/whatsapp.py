"""whatsapp client — twilio messages api.

twilio's whatsapp sandbox is free for testing and skips business verification.
sign up at twilio.com → Develop → Messaging → Try it out → Send a WhatsApp
message. you'll get a sandbox number (e.g. +14155238886) and join code.

keychain:
  twilio_account_sid   — starts with AC...
  twilio_auth_token    — the auth token from the same page
  whatsapp_from        — the sandbox number, e.g. "+14155238886"
                         or your verified production number

verbs:
- configured()
- send_message(to_e164, body)       -> dict (sid, status)
- validate_signature(url, params, signature)  -> bool   (for webhook)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Any, Optional

import httpx

from api.config import secrets
from api.observability.logging import log


def configured() -> bool:
    return bool(secrets.get("twilio_account_sid")) and bool(secrets.get("twilio_auth_token")) and bool(secrets.get("whatsapp_from"))


def _creds() -> tuple[str, str, str]:
    sid = secrets.get("twilio_account_sid")
    tok = secrets.get("twilio_auth_token")
    frm = secrets.get("whatsapp_from")
    if not (sid and tok and frm):
        raise RuntimeError(
            "whatsapp not configured. set these in the ro keychain:\n"
            "  - twilio_account_sid  (starts with AC...)\n"
            "  - twilio_auth_token\n"
            "  - whatsapp_from       (e.g. +14155238886 for sandbox)"
        )
    return sid, tok, frm


def _normalize_wa(handle: str) -> str:
    """ensure a recipient has the 'whatsapp:' prefix and a + on the number."""
    h = handle.strip()
    if h.startswith("whatsapp:"):
        rest = h[len("whatsapp:"):].strip()
        if not rest.startswith("+"):
            rest = "+" + rest.lstrip("+")
        return f"whatsapp:{rest}"
    if not h.startswith("+"):
        h = "+" + h.lstrip("+")
    return f"whatsapp:{h}"


async def send_message(to_e164: str, body: str) -> dict[str, Any]:
    sid, tok, frm = _creds()
    to = _normalize_wa(to_e164)
    from_ = _normalize_wa(frm)
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    async with httpx.AsyncClient(timeout=20.0, auth=(sid, tok)) as c:
        r = await c.post(url, data={"From": from_, "To": to, "Body": body})
        if r.status_code >= 400:
            raise RuntimeError(f"twilio whatsapp send failed: {r.status_code} {r.text[:300]}")
        data = r.json()
        return {"sid": data.get("sid"), "status": data.get("status"),
                "to": data.get("to"), "body": data.get("body")}


def validate_signature(*, url: str, form: dict[str, str], signature: str) -> bool:
    """verify a webhook came from twilio (X-Twilio-Signature header).

    https://www.twilio.com/docs/usage/webhooks/webhooks-security
    """
    tok = secrets.get("twilio_auth_token") or ""
    if not tok:
        return False
    # sort the POST params by key and append k+v pairs to the url
    base = url
    for k in sorted(form.keys()):
        base += k + form[k]
    digest = hmac.new(tok.encode(), base.encode(), hashlib.sha1).digest()
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected, signature)
