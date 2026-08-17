"""distill-down export, pure parts."""

from __future__ import annotations

from api.eval.distill import SYSTEM_PROMPT, build_pair, dedupe_pairs, refuse_below_min


def test_build_pair_shape() -> None:
    pair = build_pair("gmail", "hey, per my last email", "hey, quick bump on this")
    msgs = pair["messages"]
    assert [m["role"] for m in msgs] == ["system", "user", "assistant"]
    assert msgs[0]["content"] == SYSTEM_PROMPT
    assert "channel: gmail" in msgs[1]["content"]
    assert "hey, per my last email" in msgs[1]["content"]
    assert msgs[2]["content"] == "hey, quick bump on this"


def test_dedupe_drops_identical_keeps_order() -> None:
    a = build_pair("gmail", "draft one", "edit one")
    b = build_pair("slack", "draft two", "edit two")
    assert dedupe_pairs([a, b, a, b, a]) == [a, b]


def test_dedupe_keeps_near_duplicates() -> None:
    a = build_pair("gmail", "draft", "edit")
    b = build_pair("slack", "draft", "edit")
    assert dedupe_pairs([a, b]) == [a, b]


def test_dedupe_empty() -> None:
    assert dedupe_pairs([]) == []


def test_refuse_below_min() -> None:
    out = refuse_below_min(5, 20)
    assert out is not None
    assert out["exported"] == 0
    assert "5" in out["reason"] and "20" in out["reason"]


def test_refuse_allows_at_threshold() -> None:
    assert refuse_below_min(20, 20) is None
    assert refuse_below_min(21, 20) is None
