"""obsidian-compatible markdown vault.

mirrors the postgres tree_nodes into ~/ro/vault/ as .md files you can browse
in obsidian. one file per hour-leaf. links between files use obsidian's
[[wikilink]] syntax so you can jump around.

structure:
  ~/ro/vault/
    2026/
      05/
        13/
          14.md     # an hour
          15.md
          README.md # the day rollup (added by tree engine when day rolls up)
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

VAULT_ROOT = Path.home() / "ro" / "vault"


def _hour_file(start: datetime) -> Path:
    return VAULT_ROOT / f"{start.year:04d}" / f"{start.month:02d}" / f"{start.day:02d}" / f"{start.hour:02d}.md"


def write_hour(path: str, start: datetime, summary_md: str, events: list[dict[str, Any]]) -> None:
    """write/refresh the markdown file for an hour-leaf."""
    f = _hour_file(start)
    f.parent.mkdir(parents=True, exist_ok=True)

    front = (
        f"---\n"
        f"path: {path}\n"
        f"date: {start.strftime('%Y-%m-%d')}\n"
        f"hour: {start.strftime('%H:00 UTC')}\n"
        f"events: {len(events)}\n"
        f"---\n\n"
    )
    body = [front, f"# {start.strftime('%I:00 %p').lstrip('0').lower()} on {start.strftime('%a %b %d')}\n\n"]
    body.append(summary_md + "\n\n")
    body.append("## events\n")
    for e in events:
        ts = e.get("happened_at")
        if isinstance(ts, datetime):
            ts_str = ts.strftime("%H:%M")
        else:
            ts_str = ""
        body.append(f"- `{ts_str}` **{e.get('source', '?')}/{e.get('kind', '?')}** — {e.get('summary', '')}")
    f.write_text("\n".join(body), encoding="utf-8")


def write_rollup(path: str, start: datetime, depth: int, title: str, summary_md: str, child_titles: list[str]) -> None:
    """write a day/month/year rollup file."""
    if depth == 3:  # day
        f = VAULT_ROOT / f"{start.year:04d}" / f"{start.month:02d}" / f"{start.day:02d}" / "README.md"
    elif depth == 2:  # month
        f = VAULT_ROOT / f"{start.year:04d}" / f"{start.month:02d}" / "README.md"
    elif depth == 1:  # year
        f = VAULT_ROOT / f"{start.year:04d}" / "README.md"
    else:
        f = VAULT_ROOT / "README.md"
    f.parent.mkdir(parents=True, exist_ok=True)

    front = f"---\npath: {path}\ndepth: {depth}\n---\n\n"
    body = [front, f"# {title}\n\n", summary_md, "\n\n## children\n"]
    for ct in child_titles:
        body.append(f"- [[{ct}]]")
    f.write_text("\n".join(body), encoding="utf-8")
