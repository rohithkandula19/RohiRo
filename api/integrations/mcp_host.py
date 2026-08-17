"""mcp host. ro loads any mcp server and gains its tools.

servers are declared in mcp_servers.json (see mcp_servers.example.json).
env values support keychain refs: "keychain:github_token" resolves through
the keyring at spawn time, so the config file never holds a secret.

v1 uses a session per call: spawn the server, initialize, call, close.
about a second of overhead per call, zero lifecycle bugs. tool listings
cache for five minutes.

every mcp call is approval-gated through the normal action_log flow
(tool "mcp.call" in execute.py). ro cannot tell a read from a write on an
arbitrary server, so it asks. that is the point.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Optional

from api.config import secrets
from api.observability.logging import log

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "mcp_servers.json"
CALL_TIMEOUT_S = 60
LIST_CACHE_TTL_S = 300

_tools_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def load_config() -> dict[str, dict[str, Any]]:
    """{name: {command, args, env}} from mcp_servers.json. missing file = {}."""
    if not CONFIG_PATH.exists():
        return {}
    try:
        raw = json.loads(CONFIG_PATH.read_text())
    except Exception as e:
        log.warning("mcp_servers.json unreadable", error=str(e))
        return {}
    servers = raw.get("mcpServers") or raw.get("servers") or {}
    out: dict[str, dict[str, Any]] = {}
    for name, spec in servers.items():
        if not isinstance(spec, dict) or not spec.get("command"):
            continue
        out[str(name)] = {
            "command": str(spec["command"]),
            "args": [str(a) for a in (spec.get("args") or [])],
            "env": {str(k): str(v) for k, v in (spec.get("env") or {}).items()},
        }
    return out


def configured() -> bool:
    return bool(load_config())


def _resolve_env(env: dict[str, str]) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for k, v in env.items():
        if v.startswith("keychain:"):
            val = secrets.get(v.split(":", 1)[1])
            if val:
                resolved[k] = val
            else:
                log.warning("mcp env keychain ref missing", key=k, ref=v)
        else:
            resolved[k] = v
    return resolved


async def _with_session(name: str, fn) -> Any:
    """spawn the named server, run fn(session), tear down."""
    cfg = load_config().get(name)
    if not cfg:
        raise ValueError(f"mcp server not configured: {name}")

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=cfg["command"],
        args=cfg["args"],
        env=_resolve_env(cfg["env"]) or None,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await fn(session)


async def list_tools(name: str) -> list[dict[str, Any]]:
    """tools one server offers. cached."""
    now = time.monotonic()
    cached = _tools_cache.get(name)
    if cached and now - cached[0] < LIST_CACHE_TTL_S:
        return cached[1]

    async def _do(session) -> list[dict[str, Any]]:
        result = await session.list_tools()
        return [
            {
                "name": t.name,
                "description": (t.description or "")[:300],
            }
            for t in result.tools
        ]

    tools = await asyncio.wait_for(_with_session(name, _do), timeout=CALL_TIMEOUT_S)
    _tools_cache[name] = (now, tools)
    return tools


async def list_all_tools() -> dict[str, Any]:
    """every configured server with its tools or its error. never raises."""
    out: dict[str, Any] = {}
    for name in load_config():
        try:
            out[name] = {"ok": True, "tools": await list_tools(name)}
        except Exception as e:
            out[name] = {"ok": False, "error": str(e)[:200]}
    return out


async def call(server: str, tool: str, arguments: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """invoke one tool. returns {content, is_error}. raises on transport failure."""

    async def _do(session) -> dict[str, Any]:
        result = await session.call_tool(tool, arguments or {})
        parts: list[str] = []
        for c in result.content:
            text = getattr(c, "text", None)
            if text:
                parts.append(text)
            else:
                parts.append(f"[{getattr(c, 'type', 'content')}]")
        return {
            "content": "\n".join(parts)[:20_000],
            "is_error": bool(getattr(result, "isError", False)),
        }

    return await asyncio.wait_for(_with_session(server, _do), timeout=CALL_TIMEOUT_S)


def compact_tool_list(all_tools: dict[str, Any], limit: int = 40) -> str:
    """one-line-per-tool summary for the actions agent prompt."""
    lines: list[str] = []
    for server, info in all_tools.items():
        if not info.get("ok"):
            continue
        for t in info["tools"]:
            lines.append(f"{server}:{t['name']} — {t['description'][:80]}")
            if len(lines) >= limit:
                return "\n".join(lines)
    return "\n".join(lines)
