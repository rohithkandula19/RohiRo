"""gmail body extraction must walk nested multiparts."""

from __future__ import annotations

import base64


def _b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


def test_nested_alternative_inside_mixed() -> None:
    from api.integrations.gmail import _extract_body

    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "multipart/alternative",
                "parts": [
                    {"mimeType": "text/plain", "body": {"data": _b64("the real body")}},
                    {"mimeType": "text/html", "body": {"data": _b64("<p>the real body</p>")}},
                ],
            },
            {"mimeType": "application/pdf", "body": {"data": _b64("binary")}},
        ],
    }
    assert _extract_body(payload) == "the real body"


def test_html_only_falls_back_stripped() -> None:
    from api.integrations.gmail import _extract_body

    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/html", "body": {"data": _b64("<b>hello</b> <i>there</i>")}},
        ],
    }
    assert _extract_body(payload) == "hello there"


def test_flat_plain_still_works() -> None:
    from api.integrations.gmail import _extract_body

    payload = {"mimeType": "text/plain", "body": {"data": _b64("flat")}}
    assert _extract_body(payload) == "flat"
