"""the crew. named ro's you hire, each with a charter, collaborating.

a bot is a markdown charter in bots/<name>.md: who it is, what it owns, how
it works. each bot has a persistent session (channel_sessions channel=bot),
so it remembers its work across runs. every bot run goes through the
supervisor, which means every tool, the budget guard, the lanes, and the
approval gate apply to bots exactly as they apply to you.

collaboration is explicit, logged, and bounded: a bot delegates by writing
a line

    >> <bot-name>: <task>

in its reply. the crew runner executes those delegations (depth capped at
2, at most 3 per reply), feeds the results back to the delegating bot for
a synthesis pass, and logs every handoff to bot_messages. no hidden
channels: the whole collaboration is readable in /threads and bot_messages.

a crew run ("everyone, handle X") first asks the planner which bots the
task needs, then runs them and synthesizes. hire bots by writing charters,
or let /api/bots/draft write one from a plain-language role description.
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

BOTS_DIR = Path(__file__).resolve().parent.parent / "bots"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,32}$")
DELEGATE_RE = re.compile(r"^\s*>>\s*([a-z0-9-]{1,32})\s*:\s*(.+)$", re.MULTILINE)
MAX_DEPTH = 2
MAX_DELEGATIONS_PER_REPLY = 3
MAX_BOTS_PER_CREW = 4

CHARTER_FRAME = (
    "(you are '{name}', one named bot on the user's crew. your charter:\n"
    "---\n{charter}\n---\n"
    "other bots you may delegate to: {roster}. to delegate, write a line "
    "exactly like '>> bot-name: the task' and it will run and report back "
    "to you. delegate only what another bot is better placed to do. all "
    "outward writes still stop at the user's approval gate.)\n\n"
)


def _slug_ok(name: str) -> bool:
    return bool(SLUG_RE.match(name))


def list_bots() -> list[dict[str, Any]]:
    BOTS_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for p in sorted(BOTS_DIR.glob("*.md")):
        if not _slug_ok(p.stem):
            continue
        body = p.read_text(errors="replace")
        first = next((ln.strip("# ").strip() for ln in body.splitlines() if ln.strip()), p.stem)
        out.append({"name": p.stem, "title": first[:120], "updated_at": p.stat().st_mtime})
    return out


def get_charter(name: str) -> Optional[str]:
    if not _slug_ok(name):
        return None
    p = BOTS_DIR / f"{name}.md"
    return p.read_text(errors="replace") if p.exists() else None


def save_charter(name: str, body: str) -> None:
    if not _slug_ok(name):
        raise ValueError("bot name must be a short lowercase slug")
    if not body.strip():
        raise ValueError("charter is empty")
    BOTS_DIR.mkdir(parents=True, exist_ok=True)
    (BOTS_DIR / f"{name}.md").write_text(body)


def delete_bot(name: str) -> bool:
    if not _slug_ok(name):
        return False
    p = BOTS_DIR / f"{name}.md"
    if p.exists():
        p.unlink()
        return True
    return False


def parse_delegations(reply: str) -> list[tuple[str, str]]:
    """(bot, task) pairs a reply asked for, capped, self-delegation dropped."""
    return [
        (m.group(1), m.group(2).strip())
        for m in DELEGATE_RE.finditer(reply)
    ][:MAX_DELEGATIONS_PER_REPLY]


async def _session_for_bot(name: str) -> uuid.UUID:
    row = await db.fetchrow(
        """insert into channel_sessions (channel, chat_key) values ('bot', $1)
           on conflict (channel, chat_key) do update set chat_key = excluded.chat_key
           returning session_id""",
        name,
    )
    return row["session_id"]


async def _log_message(from_bot: str, to_bot: str, body: str) -> None:
    try:
        await db.execute(
            "insert into bot_messages (from_bot, to_bot, body) values ($1, $2, $3)",
            from_bot[:64], to_bot[:64], body[:8000],
        )
    except Exception:
        log.warning("bot message log failed")


async def run_bot(
    name: str,
    task: str,
    *,
    depth: int = 0,
    from_bot: str = "user",
) -> dict[str, Any]:
    """run one bot on one task, executing its delegations up to the caps."""
    charter = get_charter(name)
    if charter is None:
        raise ValueError(f"no bot named '{name}'. hire one on /bots.")

    allowed, why = await budget.allow_run("bot")
    if not allowed:
        return {"bot": name, "ran": False, "reason": why}

    budget.set_run(f"bot:{name}")
    await _log_message(from_bot, name, task)
    session_id = await _session_for_bot(name)

    roster = ", ".join(b["name"] for b in list_bots() if b["name"] != name) or "(none)"
    framed = CHARTER_FRAME.format(name=name, charter=charter[:4000], roster=roster) + task

    try:
        result = await run_supervisor(session_id=session_id, user_text=framed)
        reply = (result.get("text") or "").strip()
    except Exception as e:
        log.exception("bot run failed", bot=name)
        return {"bot": name, "ran": True, "error": str(e)}

    handoffs: list[dict[str, Any]] = []
    if depth < MAX_DEPTH:
        for target, subtask in parse_delegations(reply):
            if target == name or get_charter(target) is None:
                continue
            sub = await run_bot(target, subtask, depth=depth + 1, from_bot=name)
            handoffs.append(sub)
        if handoffs:
            digest = "\n\n".join(
                f"{h['bot']} reported:\n{(h.get('text') or h.get('error') or '')[:1500]}"
                for h in handoffs
            )
            await _log_message("crew", name, f"delegation results:\n{digest[:2000]}")
            try:
                synth = await run_supervisor(
                    session_id=session_id,
                    user_text=(
                        f"(your delegations came back. fold them into one final answer "
                        f"for the original task.)\n\n{digest}"
                    ),
                )
                reply = (synth.get("text") or reply).strip()
            except Exception:
                pass

    await _log_message(name, from_bot, reply[:2000])
    return {"bot": name, "ran": True, "text": reply, "handoffs": handoffs}


PLAN_PROMPT = (
    "you dispatch tasks to a crew of named bots. given the task and the "
    "roster with charters, reply with ONLY a json array of at most "
    f"{MAX_BOTS_PER_CREW} assignments: "
    '[{"bot": "<name>", "task": "<what that bot should do>"}]. '
    "involve the fewest bots that genuinely cover the task."
)


async def run_crew(task: str) -> dict[str, Any]:
    """plan which bots a task needs, run them, synthesize one answer."""
    roster = list_bots()
    if not roster:
        return {"ran": False, "reason": "no bots hired yet. create charters on /bots."}

    allowed, why = await budget.allow_run("crew")
    if not allowed:
        return {"ran": False, "reason": why}

    budget.set_run("crew:plan")
    charters = "\n\n".join(
        f"## {b['name']}\n{(get_charter(b['name']) or '')[:600]}" for b in roster
    )
    assignments: list[dict[str, str]] = []
    try:
        import json as _json
        from api.observability import llm_local
        raw = await llm_local.chat(
            system=PLAN_PROMPT, user=f"task: {task}\n\nroster:\n{charters}", max_tokens=400,
        )
        if not raw:
            from api.config import settings
            from api.observability.claude import claude_client
            resp = await claude_client.message(
                model=settings.model_cheap,
                system=PLAN_PROMPT,
                messages=[{"role": "user", "content": f"task: {task}\n\nroster:\n{charters}"}],
                max_tokens=400, temperature=0.0,
            )
            raw = "".join(b.text for b in resp.content if b.type == "text")
        raw = raw.strip().strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        parsed = _json.loads(raw)
        if isinstance(parsed, list):
            assignments = [
                {"bot": str(a.get("bot", "")), "task": str(a.get("task", task))}
                for a in parsed if get_charter(str(a.get("bot", ""))) is not None
            ][:MAX_BOTS_PER_CREW]
    except Exception:
        assignments = []
    if not assignments:
        assignments = [{"bot": roster[0]["name"], "task": task}]

    results = []
    for a in assignments:
        results.append(await run_bot(a["bot"], a["task"], from_bot="crew"))

    summary = "\n\n".join(
        f"### {r['bot']}\n{(r.get('text') or r.get('error') or r.get('reason') or '')[:2000]}"
        for r in results
    )
    return {"ran": True, "assignments": assignments, "results": results, "summary": summary}
