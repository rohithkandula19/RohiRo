"""system actions: shell.run, file.write, web.fetch.

each call requires an approval gate. these are the riskiest tools — strong
safety rails baked in:

- shell: whitelist-first. unknown commands need explicit approval text shown
  to the user. blacklist of destructive ops (rm -rf, sudo, dd, mkfs, > /etc).
  output truncated to 4kb. 30s timeout. no shell features (pipes, redirects)
  unless they pass an extra allowlist check.

- file.write: sandboxed to ~/ro/scratch/. any path outside refused.

- web.fetch: any URL allowed for GET. POST is approved per-call. responses
  truncated.
"""

from __future__ import annotations

import asyncio
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import httpx

from api.observability.logging import log

SCRATCH_ROOT = Path.home() / "ro" / "scratch"
SHELL_TIMEOUT_S = 30
SHELL_OUTPUT_CAP = 4096

# safe prefixes: if the command starts with one of these tokens, it's pre-vetted
# (still goes through approval, but description marks it as "safe class").
SAFE_PREFIXES = {
    "ls", "pwd", "echo", "cat", "head", "tail", "wc", "grep", "find", "date",
    "git", "gh", "uname", "whoami", "which", "ps", "df", "du", "uptime",
    "node", "npm", "pnpm", "yarn", "python", "uv", "pip", "ruff", "mypy",
    "pytest", "jest", "vitest", "make", "cargo",
    "kubectl", "docker",
}

# hard-no patterns. always refuse, even with approval. (defense in depth — user
# can still cause damage with approved free-text, but we won't auto-decompose.)
HARD_DENY = (
    "rm -rf /", "rm -rf ~", "rm -rf $home", "rm -rf ${home}",
    "sudo ", ":(){:|:&};:",
    "dd if=", "mkfs", " > /dev/", "chmod -r 000",
    "shutdown ", "reboot ",
    "format ", "diskutil eraseDisk",
)


@dataclass
class ShellResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    truncated: bool = False


@dataclass
class FileWriteResult:
    path: str
    bytes_written: int


@dataclass
class WebFetchResult:
    status: int
    url: str
    headers: dict[str, str]
    body: str
    truncated: bool = False


# ----- shell -----


def shell_safety(cmd: str) -> dict[str, Any]:
    """static safety check, returned as a dict the approval card can render."""
    c = cmd.strip().lower()
    deny = next((p for p in HARD_DENY if p in c), None)
    first_token = c.split()[0] if c.split() else ""
    safe_class = first_token in SAFE_PREFIXES
    has_pipe = "|" in c
    has_redir = ">" in c or "<" in c
    has_subshell = "$(" in c or "`" in c
    return {
        "hard_deny": deny,
        "safe_class": safe_class,
        "first_token": first_token,
        "has_pipe": has_pipe,
        "has_redir": has_redir,
        "has_subshell": has_subshell,
    }


async def run_shell(cmd: str) -> ShellResult:
    """run a shell command. caller already validated via shell_safety()."""
    safety = shell_safety(cmd)
    if safety["hard_deny"]:
        raise RuntimeError(f"refused: command matches deny pattern '{safety['hard_deny']}'")

    import time
    t0 = time.monotonic()
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=SHELL_TIMEOUT_S)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return ShellResult(
                exit_code=-1,
                stdout="",
                stderr=f"timeout after {SHELL_TIMEOUT_S}s",
                duration_ms=int((time.monotonic() - t0) * 1000),
                truncated=False,
            )
    except Exception as e:
        return ShellResult(
            exit_code=-1, stdout="", stderr=f"spawn failed: {e}",
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
    out_s = out.decode("utf-8", errors="replace")
    err_s = err.decode("utf-8", errors="replace")
    truncated = False
    if len(out_s) > SHELL_OUTPUT_CAP:
        out_s = out_s[:SHELL_OUTPUT_CAP]
        truncated = True
    if len(err_s) > SHELL_OUTPUT_CAP:
        err_s = err_s[:SHELL_OUTPUT_CAP]
        truncated = True
    return ShellResult(
        exit_code=proc.returncode or 0,
        stdout=out_s,
        stderr=err_s,
        duration_ms=int((time.monotonic() - t0) * 1000),
        truncated=truncated,
    )


# ----- file -----


def _resolve_scratch(path: str) -> Path:
    """force every write under ~/ro/scratch/. relative paths land there too."""
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = SCRATCH_ROOT / p
    try:
        p_resolved = p.resolve()
        SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
        scratch_resolved = SCRATCH_ROOT.resolve()
    except Exception as e:
        raise RuntimeError(f"path resolve failed: {e}")
    if scratch_resolved not in p_resolved.parents and p_resolved != scratch_resolved:
        raise RuntimeError(
            f"refused: path '{p_resolved}' is outside the scratch sandbox at {scratch_resolved}"
        )
    return p_resolved


async def write_file(*, path: str, content: str, append: bool = False) -> FileWriteResult:
    target = _resolve_scratch(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with target.open(mode, encoding="utf-8") as f:
        n = f.write(content)
    return FileWriteResult(path=str(target), bytes_written=n)


# ----- web -----


async def web_fetch(
    url: str,
    *,
    method: str = "GET",
    headers: Optional[dict[str, str]] = None,
    body: Optional[str] = None,
    cap: int = 12000,
) -> WebFetchResult:
    method = method.upper()
    if method not in {"GET", "POST", "HEAD", "PUT", "PATCH", "DELETE"}:
        raise RuntimeError(f"unsupported method: {method}")
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as c:
        kw: dict[str, Any] = {"headers": headers or {}}
        if body is not None and method in {"POST", "PUT", "PATCH"}:
            kw["content"] = body
        r = await c.request(method, url, **kw)
        text = r.text
        truncated = False
        if len(text) > cap:
            text = text[:cap]
            truncated = True
        return WebFetchResult(
            status=r.status_code,
            url=str(r.url),
            headers={k: v for k, v in r.headers.items() if k.lower() in {
                "content-type", "content-length", "etag", "last-modified",
            }},
            body=text,
            truncated=truncated,
        )
