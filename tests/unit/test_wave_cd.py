"""pure-function coverage for the moat waves."""

from __future__ import annotations


def test_ledger_hash_deterministic() -> None:
    from api.observability.ledger import _payload_sha, _row_hash

    a = _row_hash("genesis", "approval", "gmail", "a@b.c", _payload_sha({"body": "x"}))
    b = _row_hash("genesis", "approval", "gmail", "a@b.c", _payload_sha({"body": "x"}))
    c = _row_hash("genesis", "approval", "gmail", "a@b.c", _payload_sha({"body": "y"}))
    assert a == b
    assert a != c
    # dict key order must not change the sha
    assert _payload_sha({"a": 1, "b": 2}) == _payload_sha({"b": 2, "a": 1})


def test_commitments_parse() -> None:
    from api.memory.commitments import _parse

    good = '[{"direction": "mine", "who": "sam", "what": "send the deck", "due_hint": "friday"}]'
    assert _parse(good)[0]["what"] == "send the deck"
    assert _parse("```json\n[]\n```") == []
    assert _parse("not json at all") == []
    assert _parse('{"an": "object"}') == []


def test_ambient_fingerprint(tmp_path) -> None:
    from api.listeners.ambient import _fingerprint

    f = tmp_path / "a.txt"
    f.write_text("hello")
    fp1 = _fingerprint(tmp_path)
    assert str(f) in fp1
    f.write_text("changed")
    import os
    os.utime(f, (f.stat().st_atime, f.stat().st_mtime + 5))
    fp2 = _fingerprint(tmp_path)
    assert fp1[str(f)] != fp2[str(f)]


def test_lane_default_is_cloud() -> None:
    from api.observability import lanes

    assert lanes.get_lane() == "cloud"
    token = lanes.set_lane("vault")
    assert lanes.get_lane() == "vault"
    lanes.current_lane.reset(token)
    assert lanes.get_lane() == "cloud"
