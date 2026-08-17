"""ambient triggers. the machine's own events fire playbooks.

watches paths named in the `watch_paths` preference (a json list). every
30s it fingerprints each path (file mtime, or a shallow scan for a
directory) and on change fires the trigger matcher on channel "file" with
the changed path as the text — so a trigger row like
(channel=file, pattern=/Downloads/, playbook=sort-downloads) runs the
playbook whenever something lands in Downloads.

a datacenter bot cannot see your filesystem move. ro lives here.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from api.memory.db import db
from api.observability import liveness
from api.observability.logging import log

POLL_S = 30
MAX_DIR_ENTRIES = 400


async def _paths() -> list[Path]:
    try:
        row = await db.fetchrow("select value from preferences where key = 'watch_paths'")
        if not row:
            return []
        value = row["value"]
        if isinstance(value, str):
            value = json.loads(value)
        return [Path(os.path.expanduser(str(p))) for p in (value or [])][:20]
    except Exception:
        return []


def _fingerprint(path: Path) -> dict[str, float]:
    """{child_path: mtime} for a dir (shallow), {path: mtime} for a file."""
    out: dict[str, float] = {}
    try:
        if path.is_file():
            out[str(path)] = path.stat().st_mtime
        elif path.is_dir():
            for i, child in enumerate(path.iterdir()):
                if i >= MAX_DIR_ENTRIES:
                    break
                try:
                    out[str(child)] = child.stat().st_mtime
                except OSError:
                    continue
    except OSError:
        pass
    return out


async def loop() -> None:
    """background entry. quiet until watch_paths is set."""
    await asyncio.sleep(25)
    last: dict[str, dict[str, float]] = {}
    announced = False
    while True:
        try:
            paths = await _paths()
            if paths and not announced:
                log.info("ambient watcher started", paths=[str(p) for p in paths])
                announced = True
            for p in paths:
                key = str(p)
                current = await asyncio.to_thread(_fingerprint, p)
                previous = last.get(key)
                last[key] = current
                if previous is None:
                    continue  # first sight is baseline, not an event
                changed = [
                    child for child, mtime in current.items()
                    if previous.get(child) != mtime
                ]
                for child in changed[:10]:
                    from api import triggers
                    fired = await triggers.match_and_fire("file", child)
                    if fired:
                        log.info("ambient trigger fired", path=child)
            await liveness.beat("ambient_watcher", ok=True)
        except Exception as e:
            log.exception("ambient watcher iteration failed")
            await liveness.beat("ambient_watcher", ok=False, error=str(e))
        await asyncio.sleep(POLL_S)
