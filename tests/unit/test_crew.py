"""crew delegation protocol, pure parts."""

from __future__ import annotations

from api.crew import _slug_ok, parse_delegations


def test_delegation_parsing() -> None:
    reply = (
        "here's my research.\n"
        ">> penn: draft a reply to sam about the deposit\n"
        "some more prose\n"
        ">> ledger-bot: log this expense\n"
    )
    got = parse_delegations(reply)
    assert got == [
        ("penn", "draft a reply to sam about the deposit"),
        ("ledger-bot", "log this expense"),
    ]


def test_delegation_cap() -> None:
    reply = "\n".join(f">> bot{i}: task {i}" for i in range(10))
    assert len(parse_delegations(reply)) == 3


def test_prose_arrows_do_not_delegate() -> None:
    assert parse_delegations("i think x >> y in importance") == []
    assert parse_delegations("code sample: a >>= 2") == []


def test_bot_slug_rules() -> None:
    assert _slug_ok("scout")
    assert _slug_ok("ledger-bot")
    assert not _slug_ok("Scout")
    assert not _slug_ok("../evil")
