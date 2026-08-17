"""focus-aware delivery, pure parts."""

from __future__ import annotations

import json
from pathlib import Path

from api.observability import focus
from api.observability.focus import _quiet_hours_active, _read_macos_focus


def test_quiet_hours_wraps_midnight() -> None:
    spec = "22-08"
    assert _quiet_hours_active(22, spec) is True
    assert _quiet_hours_active(23, spec) is True
    assert _quiet_hours_active(0, spec) is True
    assert _quiet_hours_active(7, spec) is True
    assert _quiet_hours_active(8, spec) is False
    assert _quiet_hours_active(12, spec) is False
    assert _quiet_hours_active(21, spec) is False


def test_quiet_hours_non_wrapping() -> None:
    spec = "13-14"
    assert _quiet_hours_active(12, spec) is False
    assert _quiet_hours_active(13, spec) is True
    assert _quiet_hours_active(14, spec) is False


def test_quiet_hours_empty_spec_never_quiet() -> None:
    for hour in range(24):
        assert _quiet_hours_active(hour, "") is False


def test_quiet_hours_boundaries() -> None:
    # start inclusive, end exclusive
    assert _quiet_hours_active(9, "9-17") is True
    assert _quiet_hours_active(17, "9-17") is False
    # zero-length window means never quiet
    assert _quiet_hours_active(8, "8-8") is False


def test_quiet_hours_malformed_spec() -> None:
    assert _quiet_hours_active(12, "bananas") is False
    assert _quiet_hours_active(12, "22") is False
    assert _quiet_hours_active(12, "25-99") is False


def test_read_macos_focus_missing_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(focus, "FOCUS_ASSERTIONS_PATH", tmp_path / "nope" / "Assertions.json")
    assert _read_macos_focus() is None


def test_read_macos_focus_active(monkeypatch, tmp_path: Path) -> None:
    payload = {
        "data": [
            {
                "storeAssertionRecords": [
                    {
                        "assertionDetails": {
                            "assertionDetailsModeIdentifier": "com.apple.donotdisturb.mode.default"
                        }
                    }
                ]
            }
        ]
    }
    path = tmp_path / "Assertions.json"
    path.write_text(json.dumps(payload))
    monkeypatch.setattr(focus, "FOCUS_ASSERTIONS_PATH", path)
    assert _read_macos_focus() == "com.apple.donotdisturb.mode.default"


def test_read_macos_focus_inactive(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "Assertions.json"
    path.write_text(json.dumps({"data": [{"storeAssertionRecords": []}]}))
    monkeypatch.setattr(focus, "FOCUS_ASSERTIONS_PATH", path)
    assert _read_macos_focus() is None


def test_read_macos_focus_malformed_json(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "Assertions.json"
    path.write_text("{not json")
    monkeypatch.setattr(focus, "FOCUS_ASSERTIONS_PATH", path)
    assert _read_macos_focus() is None
