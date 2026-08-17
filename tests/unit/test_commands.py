"""slash-command routing, db-free paths."""

from __future__ import annotations

import asyncio


def test_help_answers_without_db() -> None:
    from api.listeners.commands import handle

    reply = asyncio.run(handle("/help"))
    assert reply and "/pause" in reply


def test_non_slash_falls_through() -> None:
    from api.listeners.commands import handle

    assert asyncio.run(handle("hey how's it going")) is None


def test_unknown_slash_falls_through_to_model() -> None:
    from api.listeners.commands import handle

    assert asyncio.run(handle("/shrug whatever")) is None


def test_export_prune_keeps_newest(tmp_path, monkeypatch) -> None:
    import os
    import time
    from api import export as export_mod

    monkeypatch.setattr(export_mod, "EXPORT_DIR", tmp_path)
    for i in range(5):
        p = tmp_path / f"ro-export-2026-0{i + 1}-01.tar.gz"
        p.write_bytes(b"x")
        stamp = time.time() - (5 - i) * 86400
        os.utime(p, (stamp, stamp))
    removed = export_mod.prune(keep=2)
    assert len(removed) == 3
    remaining = sorted(p.name for p in tmp_path.glob("*.tar.gz"))
    assert remaining == ["ro-export-2026-04-01.tar.gz", "ro-export-2026-05-01.tar.gz"]
