"""ro eval harness.

run a fixed task suite through the supervisor, score declarative assertions,
print a report.

usage:
  uv run python -m api.eval.harness                 # default tasks.yaml
  uv run python -m api.eval.harness --tasks foo.yaml
  uv run python -m api.eval.harness --filter actions
  uv run python -m api.eval.harness --json          # machine-readable output
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from api.supervisor import run_supervisor

DEFAULT_TASKS = Path(__file__).parent / "tasks.yaml"


@dataclass
class Failure:
    name: str
    detail: str


@dataclass
class TaskResult:
    id: str
    passed: bool
    duration_ms: int
    domains: list[str] = field(default_factory=list)
    tools_called: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    text_excerpt: str = ""
    failures: list[Failure] = field(default_factory=list)
    error: str = ""


# ----- assertions -----


def _check_domain_in(expected: list[str], domains: list[str]) -> Failure | None:
    if not expected:
        return None
    if not any(d in expected for d in domains):
        return Failure("domain_in", f"expected one of {expected}, got {domains}")
    return None


def _as_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [v]
    return list(v)


def _check_text_contains(needles: list[str], text: str) -> Failure | None:
    if not needles:
        return None
    if not any(n.lower() in text.lower() for n in needles):
        return Failure("text_contains", f"none of {needles} in response")
    return None


def _check_text_lacks(needles: list[str], text: str) -> Failure | None:
    bad = [n for n in needles if n.lower() in text.lower()]
    if bad:
        return Failure("text_lacks", f"response contained: {bad}")
    return None


def _check_text_min_length(min_len: int, text: str) -> Failure | None:
    if len(text or "") < min_len:
        return Failure("text_min_length", f"response is {len(text)} chars, want >= {min_len}")
    return None


def _check_tool_called(expected: list[str], tools: list[str]) -> Failure | None:
    if not expected:
        return None
    if not any(t in expected for t in tools):
        return Failure("tool_called", f"expected one of {expected}, got {tools}")
    return None


def _check_action_opened(expected: bool, actions: list[str]) -> Failure | None:
    if expected and not actions:
        return Failure("action_opened", "expected an approval row, got none")
    if expected is False and actions:
        return Failure("action_opened", f"expected no approval, got {actions}")
    return None


def _check_regex(pattern: str, text: str) -> Failure | None:
    if not pattern:
        return None
    if not re.search(pattern, text):
        return Failure("regex", f"regex {pattern!r} did not match")
    return None


# ----- runner -----


async def run_task(task: dict[str, Any]) -> TaskResult:
    tid = task["id"]
    text = task["input"]
    t0 = time.monotonic()
    try:
        result = await run_supervisor(session_id=uuid.uuid4(), user_text=text)
    except Exception as e:
        return TaskResult(
            id=tid, passed=False, duration_ms=int((time.monotonic() - t0) * 1000),
            error=f"supervisor raised: {e}",
            failures=[Failure("exception", str(e))],
        )

    dur = int((time.monotonic() - t0) * 1000)
    text_out = result.get("text", "") or ""
    domains = result.get("domains") or []
    actions = result.get("actions") or []
    tool_calls = result.get("tool_calls") or []
    tools_called = [tc.get("tool", "") for tc in tool_calls]

    failures: list[Failure] = []
    for f in (
        _check_domain_in(_as_list(task.get("domain_in")), domains),
        _check_text_contains(_as_list(task.get("text_contains")), text_out),
        _check_text_lacks(_as_list(task.get("text_lacks")), text_out),
        _check_text_min_length(int(task.get("text_min_length") or 0), text_out),
        _check_tool_called(_as_list(task.get("tool_called")), tools_called),
        _check_action_opened(task.get("action_opened"), actions) if "action_opened" in task else None,
        _check_regex(task.get("regex") or "", text_out),
    ):
        if f:
            failures.append(f)

    return TaskResult(
        id=tid,
        passed=not failures,
        duration_ms=dur,
        domains=domains,
        tools_called=tools_called,
        actions=actions,
        text_excerpt=text_out[:140].replace("\n", " "),
        failures=failures,
    )


async def run_suite(tasks: list[dict[str, Any]], *, concurrency: int = 4) -> list[TaskResult]:
    sem = asyncio.Semaphore(concurrency)

    async def _one(t: dict[str, Any]) -> TaskResult:
        async with sem:
            return await run_task(t)

    return await asyncio.gather(*(_one(t) for t in tasks))


# ----- output -----


def print_report(results: list[TaskResult], *, verbose: bool = False) -> int:
    passed = [r for r in results if r.passed]
    failed = [r for r in results if not r.passed]
    total_ms = sum(r.duration_ms for r in results)

    for r in results:
        mark = "✓" if r.passed else "✗"
        color_start, color_end = ("\033[32m", "\033[0m") if r.passed else ("\033[31m", "\033[0m")
        domain_str = ",".join(r.domains[:2]) if r.domains else "-"
        print(f"  {color_start}{mark}{color_end} {r.id:30s} {r.duration_ms:>5} ms   [{domain_str}]")
        if not r.passed:
            for f in r.failures:
                print(f"      └─ {f.name}: {f.detail}")
            if r.error:
                print(f"      └─ error: {r.error}")
            if r.text_excerpt:
                print(f"      └─ response: {r.text_excerpt!r}")
        elif verbose:
            if r.tools_called:
                print(f"      tools: {r.tools_called}")
            if r.text_excerpt:
                print(f"      response: {r.text_excerpt!r}")

    print()
    print(f"  passed: {len(passed)}/{len(results)}   total: {total_ms}ms   avg: {total_ms // max(1, len(results))}ms")
    return 0 if not failed else 1


def print_json(results: list[TaskResult]) -> int:
    out = [
        {
            "id": r.id, "passed": r.passed, "duration_ms": r.duration_ms,
            "domains": r.domains, "tools_called": r.tools_called, "actions": r.actions,
            "text_excerpt": r.text_excerpt,
            "failures": [{"name": f.name, "detail": f.detail} for f in r.failures],
            "error": r.error,
        }
        for r in results
    ]
    failed = sum(1 for r in results if not r.passed)
    print(json.dumps({"results": out, "passed": len(results) - failed, "failed": failed}, indent=2))
    return 0 if failed == 0 else 1


# ----- cli -----


async def _amain(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="ro eval harness")
    parser.add_argument("--tasks", default=str(DEFAULT_TASKS), help="path to tasks.yaml")
    parser.add_argument("--filter", default="", help="only run tasks whose id contains this substring")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    path = Path(args.tasks)
    if not path.exists():
        print(f"tasks file not found: {path}", file=sys.stderr)
        return 2
    doc = yaml.safe_load(path.read_text())
    tasks = doc.get("tasks") or []
    if args.filter:
        tasks = [t for t in tasks if args.filter in t.get("id", "")]
    if not tasks:
        print("no tasks matched filter.", file=sys.stderr)
        return 2

    results = await run_suite(tasks, concurrency=args.concurrency)
    if args.json:
        return print_json(results)
    return print_report(results, verbose=args.verbose)


def main() -> None:
    sys.exit(asyncio.run(_amain(sys.argv[1:])))


if __name__ == "__main__":
    main()
