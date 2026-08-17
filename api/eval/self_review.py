"""weekly self-review. ro studies its own week and gets better.

what it does, in order:
1. reads the last 7 days of action_log: what you approved untouched, what
   you edited (and how), what you rejected.
2. claude distills durable behavior rules from the rejections and edits
   ("stop proposing X", "always shorter greetings") and writes them into
   the profile's `## learned style` section, replacing last week's.
3. re-runs the voice learner so per-channel tone rules refresh.
4. runs the memory eval suite when an api key is present, so a style
   change that breaks behavior shows up as a failing eval, not a vibe.
5. reports the week + what it learned through the digest channels.

run weekly via ro.selfreview.plist, or by hand:
  uv run python -m api.eval.self_review
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from api.config import settings
from api.memory.db import db
from api.observability import budget
from api.observability.claude import claude_client
from api.observability.logging import log, setup_logging

RULES_PROMPT = (
    "you are distilling a week of a user's approve/edit/reject decisions on "
    "their agent's proposed actions into durable behavior rules for the "
    "agent. write 3-8 one-line rules, imperative, concrete, no fluff. only "
    "include rules the evidence actually supports. if the evidence is thin, "
    "write fewer rules. output only the rules as a markdown bullet list."
)


async def _week_stats() -> dict[str, Any]:
    rows = await db.fetch(
        """select status, tool, count(*) as n from action_log
           where created_at > now() - interval '7 days'
           group by status, tool order by n desc"""
    )
    return {"by_status_tool": [dict(r) for r in rows]}


async def _week_signals(limit: int = 40) -> list[dict[str, Any]]:
    rows = await db.fetch(
        """select tool, status, edit_note, description from action_log
           where created_at > now() - interval '7 days'
             and (status = 'rejected' or edit_note is not null)
           order by created_at desc limit $1""",
        limit,
    )
    return [dict(r) for r in rows]


def _replace_section(profile: str, section: str, body: str) -> str:
    """replace or append a `## <section>` block in the profile markdown."""
    lines = profile.splitlines()
    out: list[str] = []
    i = 0
    replaced = False
    header = f"## {section}"
    while i < len(lines):
        if lines[i].strip().lower() == header.lower():
            out.append(header)
            out.append("")
            out.append(body.strip())
            out.append("")
            i += 1
            while i < len(lines) and not lines[i].startswith("## "):
                i += 1
            replaced = True
            continue
        out.append(lines[i])
        i += 1
    if not replaced:
        out += ["", header, "", body.strip(), ""]
    return "\n".join(out).strip() + "\n"


async def _write_learned_style(rules_md: str) -> None:
    row = await db.fetchrow("select body from profile where id = 1")
    profile = row["body"] if row else ""
    updated = _replace_section(profile, "learned style", rules_md)
    await db.execute("update profile set body = $1, updated_at = now() where id = 1", updated)


async def _run_evals() -> dict[str, Any]:
    from api.config import secrets
    if not secrets.get("anthropic_api_key"):
        return {"ran": False, "reason": "no api key"}
    try:
        import yaml
        from pathlib import Path
        from api.eval.harness import run_suite
        tasks_file = Path(__file__).resolve().parents[2] / "tests" / "evals" / "memory_tasks.yaml"
        tasks = yaml.safe_load(tasks_file.read_text()) or []
        if isinstance(tasks, dict):
            tasks = tasks.get("tasks") or []
        results = await run_suite(tasks[:10], concurrency=2)
        passed = sum(1 for r in results if getattr(r, "passed", False))
        return {"ran": True, "passed": passed, "total": len(results)}
    except Exception as e:
        log.warning("self-review evals failed to run", error=str(e)[:200])
        return {"ran": False, "reason": str(e)[:200]}


async def run() -> None:
    setup_logging()
    budget.set_run("self-review")
    log.info("self-review starting")

    allowed, why = await budget.allow_run("self-review")
    if not allowed:
        log.warning("self-review skipped", why=why)
        return

    stats = await _week_stats()
    signals = await _week_signals()

    learned = "(no new rules this week — not enough edit or reject signals)"
    if len(signals) >= 3:
        evidence = json.dumps(signals, default=str)[:60_000]
        resp = await claude_client.message(
            model=settings.model_default,
            system=RULES_PROMPT,
            messages=[{"role": "user", "content": evidence}],
            max_tokens=500,
            temperature=0.2,
        )
        rules = "".join(b.text for b in resp.content if b.type == "text").strip()
        if rules:
            await _write_learned_style(rules)
            learned = rules

    from api.eval.voice_learner import learn_voice
    try:
        await learn_voice()
    except Exception:
        log.warning("voice learner refresh failed")

    evals = await _run_evals()

    decided = sum(r["n"] for r in stats["by_status_tool"])
    eval_line = (
        f"evals: {evals['passed']}/{evals['total']} passed" if evals.get("ran")
        else f"evals skipped ({evals.get('reason')})"
    )
    report = (
        "# weekly self-review\n\n"
        f"{decided} actions decided this week.\n\n"
        f"## what i learned\n{learned}\n\n"
        f"## checks\n{eval_line}\n"
    )
    try:
        from api.digest import deliver
        await deliver(report)
    except Exception:
        log.warning("self-review delivery failed")
    log.info("self-review done")


if __name__ == "__main__":
    asyncio.run(run())
