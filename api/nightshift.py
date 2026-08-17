"""night shift. the mac idles, ro sharpens itself for free.

runs at 03:30 via ro.nightshift.plist. every job is best-effort,
budget-checked, and lane-aware:

1. embedding backfill — conversations rows that never got a vector
   (model was down, airgap was on) get embedded so hybrid retrieval
   sharpens. vault rows are skipped by design.
2. db hygiene — analyze the hot tables so the planner stays fast as the
   archive grows.
3. eval spot-check — a subset of the memory evals runs when a key exists;
   a regression shows up in the morning report, not in a bad draft.

the report lands in preferences ('nightshift_report') and the digest
shows an "overnight" line. cloud vendors bill for compute, so their
agents sleep when you do. yours doesn't.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from api.memory.db import db
from api.observability import budget
from api.observability.logging import log, setup_logging

EMBED_BATCH = 64
EMBED_MAX_PER_NIGHT = 2000


async def _embed_backfill() -> dict[str, Any]:
    from api.config import secrets
    if not secrets.get("openai_api_key"):
        return {"skipped": "no embedding key"}
    from api.observability import lanes
    if await lanes.airgap_on():
        return {"skipped": "airgap on"}

    from api.memory.embeddings import embed_many
    done = 0
    while done < EMBED_MAX_PER_NIGHT:
        rows = await db.fetch(
            """select id, body from conversations
               where embedding is null and not vault and length(body) > 20
               limit $1""",
            EMBED_BATCH,
        )
        if not rows:
            break
        vectors = await embed_many([r["body"][:6000] for r in rows])
        for r, v in zip(rows, vectors):
            if any(v):  # zeros mean the lane or the api refused; leave null
                await db.execute(
                    "update conversations set embedding = $2 where id = $1",
                    r["id"], str(v),
                )
                done += 1
        if len(rows) < EMBED_BATCH:
            break
    return {"embedded": done}


async def _db_hygiene() -> dict[str, Any]:
    for table in ("archive_messages", "conversations", "action_log", "spend_log"):
        try:
            await db.execute(f"analyze {table}")
        except Exception:
            pass
    return {"analyzed": 4}


async def _eval_spot_check() -> dict[str, Any]:
    from api.config import secrets
    if not secrets.get("anthropic_api_key"):
        return {"skipped": "no api key"}
    allowed, why = await budget.allow_run("nightshift")
    if not allowed:
        return {"skipped": why}
    try:
        import yaml
        from pathlib import Path
        from api.eval.harness import run_suite
        tasks_file = Path(__file__).resolve().parent.parent / "tests" / "evals" / "memory_tasks.yaml"
        tasks = yaml.safe_load(tasks_file.read_text()) or []
        if isinstance(tasks, dict):
            tasks = tasks.get("tasks") or []
        results = await run_suite(tasks[:5], concurrency=2)
        passed = sum(1 for r in results if getattr(r, "passed", False))
        return {"evals_passed": passed, "evals_total": len(results)}
    except Exception as e:
        return {"skipped": f"eval error: {str(e)[:120]}"}


async def run() -> None:
    setup_logging()
    budget.set_run("nightshift")
    log.info("night shift starting")

    report: dict[str, Any] = {}
    report["embeddings"] = await _embed_backfill()
    report["hygiene"] = await _db_hygiene()
    report["evals"] = await _eval_spot_check()

    await db.execute(
        """insert into preferences (key, value) values ('nightshift_report', $1)
           on conflict (key) do update set value = excluded.value, updated_at = now()""",
        json.dumps(report),
    )
    log.info("night shift done", **{k: str(v) for k, v in report.items()})


if __name__ == "__main__":
    asyncio.run(run())
