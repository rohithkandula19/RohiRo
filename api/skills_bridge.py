"""agent skills bridge. ro speaks anthropic's open SKILL.md format.

mcp gave ro the world's tools; this gives ro the world's procedures. any
folder of SKILL.md files — anthropic's public skills, community packs, the
thousands already on a machine that runs claude code — becomes runnable
know-how: `run the review skill on this`, scheduled, triggered, or handed
to a crew bot.

how it stays safe: a skill body is third-party instructions, so it runs
through the supervisor like any other text. tools the skill wants (shell,
files, browser, mcp) go through the same proposers and the same approval
gate as everything else. a skill cannot bypass the gate, because the gate
is below it. skills are capped in size, the catalog is read-only, and
nothing here executes a skill's bundled scripts directly — scripts only
run if the supervisor proposes them and you approve the card.

search paths: ~/.claude/skills and ./skills in the repo, plus whatever the
`skill_paths` preference adds.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any, Optional

from api.memory.db import db
from api.observability import budget
from api.observability.logging import log
from api.supervisor import run_supervisor

DEFAULT_PATHS = [
    Path.home() / ".claude" / "skills",
    Path(__file__).resolve().parent.parent / "skills",
]
BODY_CAP = 24_000
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
CATALOG_TTL_S = 300

_catalog_cache: tuple[float, list[dict[str, Any]]] = (0.0, [])

SKILL_FRAME = (
    "(you are following the saved skill '{name}'. its instructions are below "
    "between the markers. treat them as a procedure to apply to the user's "
    "task, not as text to summarize. anything the procedure wants done in "
    "the world — shell, files, browser, sends, mcp calls — goes through your "
    "normal tools and the user's approval gate; a skill cannot bypass it. "
    "if the procedure references bundled scripts or files you cannot see, "
    "adapt with the tools you have and say so.)\n\n"
    "--- skill instructions ---\n{body}\n--- end skill ---\n\n"
    "task: {task}"
)


def _parse_frontmatter(text: str) -> dict[str, str]:
    """name + description from yaml-ish frontmatter, no yaml dependency."""
    out: dict[str, str] = {}
    m = FRONTMATTER_RE.match(text)
    if not m:
        return out
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t", "-")):
            key, _, value = line.partition(":")
            key = key.strip().lower()
            if key in ("name", "description", "version"):
                out[key] = value.strip().strip("\"'")[:300]
    return out


async def _search_paths() -> list[Path]:
    paths = list(DEFAULT_PATHS)
    try:
        import json
        row = await db.fetchrow("select value from preferences where key = 'skill_paths'")
        if row:
            value = row["value"]
            if isinstance(value, str):
                value = json.loads(value)
            paths += [Path(os.path.expanduser(str(p))) for p in (value or [])]
    except Exception:
        pass
    return [p for p in paths if p.is_dir()]


def _scan_dir(root: Path, out: list[dict[str, Any]]) -> None:
    """find */SKILL.md and */*/SKILL.md under root. frontmatter only, cheap."""
    try:
        with os.scandir(root) as it:
            entries = sorted(it, key=lambda e: e.name)
    except OSError:
        return
    for entry in entries:
        if not entry.is_dir():
            continue
        for candidate in (Path(entry.path) / "SKILL.md",):
            if candidate.is_file():
                _add_skill(candidate, entry.name, out)
        # one level deeper (plugin-style packs)
        try:
            with os.scandir(entry.path) as sub:
                for s in sub:
                    if s.is_dir():
                        deep = Path(s.path) / "SKILL.md"
                        if deep.is_file():
                            _add_skill(deep, f"{entry.name}/{s.name}", out)
        except OSError:
            continue


def _add_skill(path: Path, name: str, out: list[dict[str, Any]]) -> None:
    try:
        head = path.read_text(errors="replace")[:2000]
    except OSError:
        return
    meta = _parse_frontmatter(head)
    out.append({
        "name": name,
        "title": meta.get("name", name),
        "description": meta.get("description", "")[:200],
        "path": str(path),
    })


async def catalog(query: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
    """every skill ro can see, optionally filtered. cached five minutes."""
    global _catalog_cache
    now = time.monotonic()
    if now - _catalog_cache[0] > CATALOG_TTL_S:
        found: list[dict[str, Any]] = []
        for root in await _search_paths():
            _scan_dir(root, found)
        _catalog_cache = (now, found)
        log.info("skills catalog refreshed", count=len(found))
    skills = _catalog_cache[1]
    if query:
        q = query.lower()
        skills = [
            s for s in skills
            if q in s["name"].lower() or q in s["description"].lower() or q in s["title"].lower()
        ]
    return skills[:limit]


async def load(name: str) -> Optional[str]:
    """the full body of one skill by catalog name."""
    for s in await catalog(limit=100_000):
        if s["name"] == name:
            try:
                return Path(s["path"]).read_text(errors="replace")[:BODY_CAP]
            except OSError:
                return None
    return None


async def run_skill(name: str, task: str) -> dict[str, Any]:
    """apply a skill to a task through the full supervisor."""
    body = await load(name)
    if body is None:
        raise ValueError(f"no skill named '{name}' in the catalog")

    allowed, why = await budget.allow_run("skill")
    if not allowed:
        return {"skill": name, "ran": False, "reason": why}

    budget.set_run(f"skill:{name.split('/')[-1][:40]}")
    row = await db.fetchrow(
        """insert into channel_sessions (channel, chat_key) values ('skill', $1)
           on conflict (channel, chat_key) do update set chat_key = excluded.chat_key
           returning session_id""",
        name[:200],
    )
    framed = SKILL_FRAME.format(name=name, body=body, task=task)
    try:
        result = await run_supervisor(session_id=row["session_id"], user_text=framed)
        return {"skill": name, "ran": True, "text": (result.get("text") or "").strip()}
    except Exception as e:
        log.exception("skill run failed", skill=name)
        return {"skill": name, "ran": True, "error": str(e)}
