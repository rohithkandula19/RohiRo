"""fork and estate export. your whole agent as an archive you own.

produces ~/ro-exports/ro-export-<date>.tar.gz containing:
- ro.dump: the full postgres database (memory, approvals history, spend,
  ledger, archive, dossiers, commitments — everything)
- playbooks/: your playbook markdown
- mcp_servers.json (keychain refs only; no secret material)
- RESTORE.md: exact restore steps

secrets are NOT exported — they live in the keychain and stay there.
restore on any machine with this repo: create the db, pg_restore the dump,
copy playbooks back, re-enter keys. the agent is a folder, not an account.

run:  uv run python -m api.export      (or: ro export)
"""

from __future__ import annotations

import asyncio
import datetime
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from api.config import settings

ROOT = Path(__file__).resolve().parent.parent
EXPORT_DIR = Path.home() / "ro-exports"

RESTORE_MD = """# restoring ro from this export

1. clone the repo and run ./scripts/bootstrap.sh (starts postgres, applies schema).
2. restore the database:
   pg_restore --clean --if-exists -d <your postgres_url> ro.dump
3. copy playbooks/ back into the repo's playbooks/ directory.
4. copy mcp_servers.json to the repo root (it holds keychain refs, not secrets).
5. re-enter secrets into the keychain (scripts/setup_keys.sh) — secrets are
   never exported.
6. uv run ro up

your memory, approval history, ledger, archive, dossiers, and playbooks are
all in the dump. the agent is yours; this file proves it.
"""


def _pg_dump(dest: Path) -> None:
    url = settings.postgres_url
    cmd = shutil.which("pg_dump") or "/opt/homebrew/opt/postgresql@17/bin/pg_dump"
    result = subprocess.run(
        [cmd, "-Fc", "-f", str(dest), url],
        capture_output=True, text=True, timeout=600,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump failed: {result.stderr[:400]}")


async def export() -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.date.today().isoformat()
    out = EXPORT_DIR / f"ro-export-{stamp}.tar.gz"

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        await asyncio.to_thread(_pg_dump, tmpdir / "ro.dump")
        (tmpdir / "RESTORE.md").write_text(RESTORE_MD)

        with tarfile.open(out, "w:gz") as tar:
            tar.add(tmpdir / "ro.dump", arcname="ro.dump")
            tar.add(tmpdir / "RESTORE.md", arcname="RESTORE.md")
            playbooks = ROOT / "playbooks"
            if playbooks.exists():
                tar.add(playbooks, arcname="playbooks")
            mcp = ROOT / "mcp_servers.json"
            if mcp.exists():
                tar.add(mcp, arcname="mcp_servers.json")
    return out


def prune(keep: int = 7) -> list[str]:
    """keep the newest n exports, delete the rest. returns removed names."""
    if not EXPORT_DIR.exists():
        return []
    exports = sorted(EXPORT_DIR.glob("ro-export-*.tar.gz"),
                     key=lambda p: p.stat().st_mtime, reverse=True)
    removed = []
    for old in exports[max(1, keep):]:
        old.unlink()
        removed.append(old.name)
    return removed


async def main() -> None:
    import sys
    path = await export()
    print(f"exported: {path}")
    if "--rotate" in sys.argv:
        try:
            idx = sys.argv.index("--rotate")
            keep = int(sys.argv[idx + 1]) if len(sys.argv) > idx + 1 else 7
        except (ValueError, IndexError):
            keep = 7
        removed = prune(keep)
        if removed:
            print(f"rotated out: {', '.join(removed)}")
    print("restore instructions are inside (RESTORE.md). secrets stay in your keychain.")


if __name__ == "__main__":
    asyncio.run(main())
