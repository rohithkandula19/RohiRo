"""web push. vapid keys in keychain, subscriptions in postgres.

v1 scope is the localhost web ui (service workers get a secure-context pass
on localhost). the remote path needs https via a tailscale cert, noted in
docs. pushes fire on approval-needed and digest-ready. dead subscriptions
(410/404) are pruned on send.

generate keys once:  uv run python -m api.integrations.webpush --generate
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from api.config import secrets
from api.memory.db import db
from api.observability.logging import log

VAPID_SUB_DEFAULT = "mailto:ro@localhost"


def configured() -> bool:
    return bool(secrets.get("vapid_private_key"))


def public_key() -> str:
    return secrets.get("vapid_public_key") or ""


async def save_subscription(sub: dict[str, Any]) -> None:
    endpoint = sub.get("endpoint") or ""
    if not endpoint:
        raise ValueError("subscription missing endpoint")
    await db.execute(
        """insert into push_subscriptions (endpoint, subscription)
           values ($1, $2)
           on conflict (endpoint) do update set subscription = excluded.subscription""",
        endpoint, json.dumps(sub),
    )


async def _delete_subscription(endpoint: str) -> None:
    await db.execute("delete from push_subscriptions where endpoint = $1", endpoint)


def _send_one(subscription: dict[str, Any], payload: str, private_key: str, sub_email: str) -> None:
    from pywebpush import webpush
    webpush(
        subscription_info=subscription,
        data=payload,
        vapid_private_key=private_key,
        vapid_claims={"sub": sub_email},
    )


async def push_all(*, title: str, body: str, url: str = "/") -> dict[str, int]:
    """send to every subscription. prunes dead ones. never raises."""
    if not configured():
        return {"skipped": 1}
    private_key = secrets.get("vapid_private_key") or ""
    sub_email = secrets.get("vapid_subject") or VAPID_SUB_DEFAULT
    payload = json.dumps({"title": title[:120], "body": body[:400], "url": url})

    rows = await db.fetch("select endpoint, subscription from push_subscriptions")
    sent = 0
    pruned = 0
    for r in rows:
        sub = r["subscription"]
        if isinstance(sub, str):
            try:
                sub = json.loads(sub)
            except Exception:
                await _delete_subscription(r["endpoint"])
                pruned += 1
                continue
        try:
            await asyncio.to_thread(_send_one, sub, payload, private_key, sub_email)
            sent += 1
        except Exception as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (404, 410):
                await _delete_subscription(r["endpoint"])
                pruned += 1
            else:
                log.warning("web push send failed", error=str(e)[:200])
    return {"sent": sent, "pruned": pruned}


def _generate() -> None:
    """one-time key generation into the keychain."""
    import keyring
    from py_vapid import Vapid, b64urlencode
    from cryptography.hazmat.primitives import serialization

    v = Vapid()
    v.generate_keys()
    private_pem = v.private_pem().decode()
    raw_pub = v.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    public_b64 = b64urlencode(raw_pub)
    keyring.set_password("ro", "vapid_private_key", private_pem)
    keyring.set_password("ro", "vapid_public_key", public_b64)
    print("vapid keys saved to keychain (vapid_private_key, vapid_public_key)")
    print(f"public key: {public_b64}")


if __name__ == "__main__":
    import sys
    if "--generate" in sys.argv:
        _generate()
    else:
        print("usage: python -m api.integrations.webpush --generate")
