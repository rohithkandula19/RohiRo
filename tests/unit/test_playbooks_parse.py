"""playbook parsing and naming rules."""

from __future__ import annotations

from api.playbooks import _slug_ok, _split_steps


def test_no_headings_is_one_step() -> None:
    steps = _split_steps("# title\njust do the thing.")
    assert len(steps) == 1
    assert "do the thing" in steps[0]


def test_step_headings_chain() -> None:
    body = "# scan\n## step research\nlook things up.\n## step brief\nwrite it up."
    steps = _split_steps(body)
    assert len(steps) == 2
    assert "look things up" in steps[0]
    assert "# scan" in steps[0]  # preamble folds into step 1
    assert "write it up" in steps[1]


def test_step_cap() -> None:
    body = "\n".join(f"## step {i}\ndo {i}" for i in range(30))
    assert len(_split_steps(body)) <= 12


def test_slug_rules() -> None:
    assert _slug_ok("morning-scan")
    assert _slug_ok("a1")
    assert not _slug_ok("Bad Name")
    assert not _slug_ok("../escape")
    assert not _slug_ok("")
