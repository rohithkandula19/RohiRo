"""browser trust tier policy, pure parts."""

from __future__ import annotations

from api.observability.trust import _domain, _tier_for


def test_domain_extraction() -> None:
    assert _domain("https://mail.google.com/u/0") == "mail.google.com"
    assert _domain("not a url") == ""


def test_tier_matching_with_subdomains() -> None:
    table = {"google.com": "read", "github.com": "navigate"}
    assert _tier_for("mail.google.com", table) == "read"
    assert _tier_for("github.com", table) == "navigate"
    assert _tier_for("api.github.com", table) == "navigate"
    assert _tier_for("evil-github.com", table) is None
    assert _tier_for("github.com.evil.example", table) is None
    assert _tier_for("", table) is None
