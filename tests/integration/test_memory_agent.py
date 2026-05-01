"""tests for the memory agent's local helpers.

these don't call claude. the model is wired in but the section editor and
parser are pure python and worth pinning.
"""

from __future__ import annotations

from api.agents.memory.agent import _parse, _replace_section


def test_parse_handles_fences() -> None:
    raw = '```json\n{"action": "read", "say": "hi"}\n```'
    out = _parse(raw)
    assert out["action"] == "read"
    assert out["say"] == "hi"


def test_parse_handles_plain_text() -> None:
    out = _parse("hello there")
    assert out["action"] == "read"
    assert out["say"] == "hello there"


def test_replace_section_appends_when_missing() -> None:
    profile = "# profile\n\n## who\n- name: ro\n"
    new = _replace_section(profile, "fitness", "- 5 runs/week")
    assert "## fitness" in new
    assert "5 runs/week" in new
    assert "- name: ro" in new


def test_replace_section_replaces_existing() -> None:
    profile = "# profile\n\n## fitness\n- old goal\n\n## who\n- name: ro\n"
    new = _replace_section(profile, "fitness", "- new goal")
    assert "new goal" in new
    assert "old goal" not in new
    assert "- name: ro" in new
