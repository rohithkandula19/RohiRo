"""playbooks. teach ro a task once, run it forever.

v1 is run-verbatim: a playbook is a markdown file under playbooks/ whose body
is fed to the supervisor. `## step` headings make it a chain: steps run in
order through the same session, each step seeing a digest of what came
before. that is agent coordination in its deterministic form — the research
step's output feeds the drafting step — with every hop in the traces.

rules that keep playbooks safe:
- runs go through run_supervisor, so every outward write hits the same
  approval gate as everything else. a playbook cannot bypass it.
- each run is budget-checked and attributed (playbook:<name>).
- each step is instruction-constrained: outward messages may only target the
  owner unless the playbook explicitly names a recipient, and shell commands
  always need the approval card.

schedule one with a schedules row whose text is `playbook:<name>`.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any, Optional

from api.memory.db import db
from api.observability import budget
from api.observability.logging import log
from api.supervisor import run_supervisor

PLAYBOOK_DIR = Path(__file__).resolve().parent.parent / "playbooks"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
MAX_STEPS = 12
STEP_CONTEXT_CHARS = 2000

GUARDRAIL = (
    "(you are running the saved playbook '{name}', step {k} of {n}. "
    "outward messages may only go to the owner unless this playbook text "
    "explicitly names another recipient. shell commands and any outward "
    "write still require approval as usual.)\n\n"
)


def _slug_ok(name: str) -> bool:
    return bool(SLUG_RE.match(name))


def _path(name: str) -> Path:
    return PLAYBOOK_DIR / f"{name}.md"


def list_playbooks() -> list[dict[str, Any]]:
    PLAYBOOK_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for p in sorted(PLAYBOOK_DIR.glob("*.md")):
        # only valid slugs are runnable; skip README and anything else
        if not _slug_ok(p.stem):
            continue
        body = p.read_text(errors="replace")
        first = next((ln.strip("# ").strip() for ln in body.splitlines() if ln.strip()), p.stem)
        out.append({
            "name": p.stem,
            "title": first[:120],
            "steps": max(1, len(_split_steps(body))),
            "updated_at": p.stat().st_mtime,
        })
    return out


def get_playbook(name: str) -> Optional[str]:
    if not _slug_ok(name):
        return None
    p = _path(name)
    return p.read_text(errors="replace") if p.exists() else None


def save_playbook(name: str, body: str) -> None:
    if not _slug_ok(name):
        raise ValueError("playbook name must be a lowercase slug (a-z, 0-9, dashes)")
    if not body.strip():
        raise ValueError("playbook body is empty")
    PLAYBOOK_DIR.mkdir(parents=True, exist_ok=True)
    _path(name).write_text(body)


def delete_playbook(name: str) -> bool:
    if not _slug_ok(name):
        return False
    p = _path(name)
    if p.exists():
        p.unlink()
        return True
    return False


def _split_steps(body: str) -> list[str]:
    """split on `## step` headings. no headings = one step, the whole body."""
    parts = re.split(r"(?im)^##\s*step\b[^\n]*$", body)
    steps = [s.strip() for s in parts if s.strip()]
    if len(steps) <= 1:
        return [body.strip()]
    # part 0 is the preamble before the first heading; fold it into step 1
    if not re.match(r"(?im)^##\s*step\b", body.strip()):
        preamble, rest = steps[0], steps[1:]
        if rest:
            rest[0] = f"{preamble}\n\n{rest[0]}"
            steps = rest
    return steps[:MAX_STEPS]


async def run_playbook(name: str) -> dict[str, Any]:
    """run a playbook end to end. returns per-step results."""
    body = get_playbook(name)
    if body is None:
        raise ValueError(f"playbook not found: {name}")

    allowed, why = await budget.allow_run("playbook")
    if not allowed:
        return {"name": name, "ran": False, "reason": why, "steps": []}

    budget.set_run(f"playbook:{name}")

    # stable session per playbook so repeated runs keep context
    row = await db.fetchrow(
        """insert into channel_sessions (channel, chat_key) values ('playbook', $1)
           on conflict (channel, chat_key) do update set chat_key = excluded.chat_key
           returning session_id""",
        name,
    )
    session_id: uuid.UUID = row["session_id"]

    steps = _split_steps(body)
    results: list[dict[str, Any]] = []
    prior_digest = ""
    for k, step in enumerate(steps, start=1):
        prompt = GUARDRAIL.format(name=name, k=k, n=len(steps)) + step
        if prior_digest:
            prompt += f"\n\n(context from the previous step:\n{prior_digest})"
        try:
            result = await run_supervisor(session_id=session_id, user_text=prompt)
            text = (result.get("text") or "").strip()
            results.append({"step": k, "ok": True, "text": text[:4000]})
            prior_digest = text[:STEP_CONTEXT_CHARS]
        except Exception as e:
            log.exception("playbook step failed", playbook=name, step=k)
            results.append({"step": k, "ok": False, "error": str(e)})
            # halt on failure, report what completed. partial honesty.
            break

    return {"name": name, "ran": True, "steps": results,
            "completed": sum(1 for r in results if r.get("ok")), "total": len(steps)}
