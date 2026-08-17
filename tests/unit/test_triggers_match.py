"""trigger pattern matching."""

from __future__ import annotations

from api.triggers import _matches


def test_substring_case_insensitive() -> None:
    assert _matches("Invoice", "your INVOICE #42 is attached")
    assert not _matches("invoice", "nothing to see")


def test_regex_form() -> None:
    assert _matches(r"/invoice #\d+/", "invoice #42 attached")
    assert not _matches(r"/invoice #\d+/", "invoice attached")


def test_bad_regex_never_raises() -> None:
    assert not _matches("/[unclosed/", "anything")


def test_slashes_inside_substring() -> None:
    assert _matches("a/b", "path a/b here")
