"""actions sub-agent.

handles "do an arbitrary thing for me" requests that don't fit the comms/
calendar/code/etc verticals:

  - shell.run    "run pytest in rohflow" / "git status in ~/foo"
  - file.write   "save a note titled X with body Y" / "create todo.md saying ..."
  - web.fetch    "fetch the json from https://api.foo/bar"

every action goes through approval. nothing executes inline.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from typing import Any

from api.agents.base import Agent, AgentResult
from api.config import settings
from api.integrations import system
from api.observability.logging import log
from api.supervisor import approval

INTENT_PROMPT = """ro asked you to do an "action." pick the most likely tool and
extract its parameters as strict JSON.

tools:

1) "shell" — run a shell command.
   params: { "tool": "shell", "command": "<full command>", "reason": "<one-line why>" }

2) "file" — write/append a file inside ro's scratch dir.
   params: { "tool": "file", "path": "<relative path>", "content": "<text>", "append": false }

3) "web" — plain http fetch (json apis, plain html).
   params: { "tool": "web", "url": "<full url>", "method": "GET" }

4) "browser" — one-shot chromium render (screenshot + text). good for "show me
   what's at <url>".
   params: { "tool": "browser", "url": "<full url>" }

5) "browser_step" — a persistent browser session. use this for multi-step web
   tasks where ro will do several actions on the same site, one approval at a
   time. sub-actions:
      goto      open or navigate to a url            params: {step: "goto",  url}
      click     click a button/link by visible text  params: {step: "click", text}
      fill      fill an input by its label/placeholder
                                                     params: {step: "fill",  label, value}
      scroll    scroll the page by N pixels          params: {step: "scroll", pixels}
      close     close the session                    params: {step: "close"}
   params: { "tool": "browser_step", "step": "...", "url": "...", "text": "...",
             "label": "...", "value": "...", "pixels": 600 }

6) "vision" — answer a question about an image. source is a local path
   (under ~/ or ~/ro/scratch) or a public https URL. uses claude vision.
   examples: "what's in this screenshot", "describe ~/Downloads/x.png",
   "OCR this image".
   params: { "tool": "vision", "source": "<path or https url>",
             "prompt": "<question; default: describe>" }

7) "mcp" — a tool from a connected mcp server (listed below, format
   server:tool). use when the request maps to one of those better than the
   built-ins.
   params: { "tool": "mcp", "server": "<server>", "mcp_tool": "<tool>",
             "arguments": { ... }, "reason": "<one-line why>" }

8) "none" — the request doesn't clearly map to any of the above.

connected mcp tools (empty means none configured):
{mcp_tools}

reply with ONLY a JSON object. nothing else."""


class ActionsAgent(Agent):
    async def run(self, *, session_id: str, user_text: str, context: dict[str, Any]) -> AgentResult:
        spec = await self._plan(user_text)
        tool = spec.get("tool", "none")

        if tool == "shell":
            return await self._propose_shell(spec, user_text, session_id)
        if tool == "file":
            return await self._propose_file(spec, user_text, session_id)
        if tool == "web":
            return await self._propose_web(spec, user_text, session_id)
        if tool == "browser":
            return await self._propose_browser(spec, user_text, session_id)
        if tool == "browser_step":
            return await self._propose_browser_step(spec, user_text, session_id)
        if tool == "vision":
            return await self._propose_vision(spec, user_text, session_id)
        if tool == "mcp":
            return await self._propose_mcp(spec, user_text, session_id)

        return AgentResult(
            text=(
                "i can run shell commands, write files in my scratch dir, or fetch web "
                "urls — but i couldn't decide which one you meant. try one of:\n"
                "  • \"run `git status` in ~/RohiRo\"\n"
                "  • \"save a note titled 'todo' with body 'ship slack'\"\n"
                "  • \"fetch https://api.github.com/users/rohithkandula937\""
            ),
        )

    # ----- proposers (each opens approval, never executes inline) -----

    async def _propose_mcp(self, spec: dict[str, Any], user_text: str, session_id: str) -> AgentResult:
        server = (spec.get("server") or "").strip()
        mcp_tool = (spec.get("mcp_tool") or "").strip()
        arguments = spec.get("arguments") or {}
        if not server or not mcp_tool:
            return AgentResult(text="i need both the mcp server and the tool name.")

        from api.integrations import mcp_host
        if server not in mcp_host.load_config():
            return AgentResult(text=f"no mcp server named '{server}' is configured.")

        reason = (spec.get("reason") or user_text)[:140]
        action_id = await approval.open_approval(
            session_id=uuid.UUID(session_id),
            domain="actions",
            tool="mcp.call",
            description=f"mcp {server}:{mcp_tool} {json.dumps(arguments)[:120]}",
            payload={"server": server, "mcp_tool": mcp_tool,
                     "arguments": arguments, "reason": reason},
            requires_approval=True,
        )
        return AgentResult(
            text=(
                f"i'll call `{server}:{mcp_tool}` with:\n\n```json\n"
                f"{json.dumps(arguments, indent=2)[:800]}\n```\n\napprove to run it."
            ),
            actions_opened=[str(action_id)],
        )

    async def _propose_shell(self, spec: dict[str, Any], user_text: str, session_id: str) -> AgentResult:
        cmd = (spec.get("command") or "").strip()
        if not cmd:
            return AgentResult(text="i need a concrete command to run.")
        safety = system.shell_safety(cmd)
        if safety["hard_deny"]:
            return AgentResult(
                text=f"refusing: that command matches a hard-deny pattern (`{safety['hard_deny']}`). i won't even ask for approval on this.",
                error="hard_deny",
            )

        reason = (spec.get("reason") or user_text)[:140]
        action_id = await approval.open_approval(
            session_id=uuid.UUID(session_id),
            domain="actions",
            tool="shell.run",
            description=f"run `{cmd[:120]}`",
            payload={"command": cmd, "reason": reason, "safety": safety},
            requires_approval=True,
        )

        flags: list[str] = []
        if not safety["safe_class"]:
            flags.append("unfamiliar command")
        if safety["has_pipe"]:
            flags.append("pipe")
        if safety["has_redir"]:
            flags.append("redirect")
        if safety["has_subshell"]:
            flags.append("subshell")

        return AgentResult(
            text=f"i'll run this if you approve:\n\n```\n{cmd}\n```",
            actions_opened=[str(action_id)],
            tool_calls=[{
                "tool": "shell.draft",
                "args": {"reason": reason},
                "result": {
                    "command": cmd,
                    "reason": reason,
                    "safe_class": safety["safe_class"],
                    "first_token": safety["first_token"],
                    "flags": flags,
                },
            }],
        )

    async def _propose_file(self, spec: dict[str, Any], user_text: str, session_id: str) -> AgentResult:
        path = (spec.get("path") or "").strip()
        content = spec.get("content") or ""
        append = bool(spec.get("append", False))
        if not path or not content:
            return AgentResult(text="i need a path and content to write the file.")

        action_id = await approval.open_approval(
            session_id=uuid.UUID(session_id),
            domain="actions",
            tool="file.write",
            description=f"{'append to' if append else 'write'} ~/ro/scratch/{path}",
            payload={"path": path, "content": content, "append": append},
            requires_approval=True,
        )
        preview = content if len(content) <= 320 else content[:320] + "…"
        return AgentResult(
            text=f"i'll write to `~/ro/scratch/{path}`:\n\n```\n{preview}\n```",
            actions_opened=[str(action_id)],
            tool_calls=[{
                "tool": "file.draft",
                "args": {"path": path, "append": append},
                "result": {"path": path, "append": append, "content": content,
                           "bytes": len(content.encode("utf-8"))},
            }],
        )

    async def _propose_browser(self, spec: dict[str, Any], user_text: str, session_id: str) -> AgentResult:
        url = (spec.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            return AgentResult(text="i need a full https:// url to render.")

        # trusted domain? render without a card (standing rule the user set).
        from api.observability import trust
        if await trust.browser_auto("browser.render", url):
            action_id = await approval.open_approval(
                session_id=uuid.UUID(session_id),
                domain="actions",
                tool="browser.render",
                description=f"[trusted] render {url[:80]}",
                payload={"url": url},
                requires_approval=False,
            )
            from api.supervisor import execute as execute_mod
            result = await execute_mod.execute(action_id)
            if result.get("ok"):
                page = result.get("result", {})
                return AgentResult(
                    text=f"opened `{url}` (trusted domain):\n\n{(page.get('text') or '')[:1500]}",
                    actions_opened=[str(action_id)],
                )
            return AgentResult(text=f"trusted render failed: {result.get('error')}")

        action_id = await approval.open_approval(
            session_id=uuid.UUID(session_id),
            domain="actions",
            tool="browser.render",
            description=f"render {url[:80]}",
            payload={"url": url},
            requires_approval=True,
        )
        return AgentResult(
            text=f"i'll open `{url}` in a chromium tab and show you what's on the page.",
            actions_opened=[str(action_id)],
            tool_calls=[{
                "tool": "browser.draft",
                "args": {},
                "result": {"url": url},
            }],
        )

    async def _propose_browser_step(self, spec: dict[str, Any], user_text: str, session_id: str) -> AgentResult:
        step = (spec.get("step") or "").strip().lower()
        if step not in {"goto", "click", "fill", "scroll", "close"}:
            return AgentResult(text="i need a clear sub-step: goto / click / fill / scroll / close.")
        # build the payload depending on the step
        if step == "goto":
            url = (spec.get("url") or "").strip()
            if not url.startswith(("http://", "https://")):
                return AgentResult(text="i need a full https:// url for goto.")
            desc = f"open `{url}`"
            payload = {"step": "goto", "session_key": session_id, "url": url}
        elif step == "click":
            target = (spec.get("text") or "").strip()
            if not target:
                return AgentResult(text="what should i click? give me the visible text on the button or link.")
            desc = f"click `{target[:60]}`"
            payload = {"step": "click", "session_key": session_id, "text": target}
        elif step == "fill":
            label = (spec.get("label") or "").strip()
            value = (spec.get("value") or "").strip()
            if not label or not value:
                return AgentResult(text="fill needs both the input label and the value to type.")
            desc = f"fill `{label[:40]}` with `{value[:40]}`"
            payload = {"step": "fill", "session_key": session_id, "label": label, "value": value}
        elif step == "scroll":
            pixels = int(spec.get("pixels") or 600)
            desc = f"scroll {pixels}px"
            payload = {"step": "scroll", "session_key": session_id, "pixels": pixels}
        else:  # close
            desc = "close the browser session"
            payload = {"step": "close", "session_key": session_id}

        # trusted-domain goto runs without a card. clicks, fills, scrolls,
        # and closes always ask — only url-bearing actions can be auto.
        from api.observability import trust
        if step == "goto" and await trust.browser_auto("browser.goto", payload.get("url")):
            action_id = await approval.open_approval(
                session_id=uuid.UUID(session_id),
                domain="actions",
                tool="browser.step",
                description=f"[trusted] {desc}",
                payload=payload,
                requires_approval=False,
            )
            from api.supervisor import execute as execute_mod
            result = await execute_mod.execute(action_id)
            if result.get("ok"):
                page = result.get("result", {})
                return AgentResult(
                    text=f"went there (trusted domain). {page.get('title') or ''}\n\n{(page.get('text') or '')[:1200]}",
                    actions_opened=[str(action_id)],
                )
            return AgentResult(text=f"trusted goto failed: {result.get('error')}")

        action_id = await approval.open_approval(
            session_id=uuid.UUID(session_id),
            domain="actions",
            tool="browser.step",
            description=desc,
            payload=payload,
            requires_approval=True,
        )
        return AgentResult(
            text=f"next browser step: {desc}",
            actions_opened=[str(action_id)],
            tool_calls=[{
                "tool": "browser_step.draft",
                "args": {"step": step},
                "result": payload,
            }],
        )

    async def _propose_vision(self, spec: dict[str, Any], user_text: str, session_id: str) -> AgentResult:
        source = (spec.get("source") or "").strip()
        prompt = (spec.get("prompt") or "describe this image.").strip()
        if not source:
            return AgentResult(text="give me a local file path or an https url to a public image.")
        kind = "url" if source.startswith(("http://", "https://")) else "path"
        action_id = await approval.open_approval(
            session_id=uuid.UUID(session_id),
            domain="actions",
            tool="vision.ask",
            description=f"vision: {source[:80]}",
            payload={"source": source, "kind": kind, "prompt": prompt},
            requires_approval=True,
        )
        return AgentResult(
            text=f"i'll look at `{source}` and answer: \"{prompt}\"",
            actions_opened=[str(action_id)],
            tool_calls=[{
                "tool": "vision.draft",
                "args": {},
                "result": {"source": source, "kind": kind, "prompt": prompt},
            }],
        )

    async def _propose_web(self, spec: dict[str, Any], user_text: str, session_id: str) -> AgentResult:
        url = (spec.get("url") or "").strip()
        method = (spec.get("method") or "GET").upper()
        if not url.startswith(("http://", "https://")):
            return AgentResult(text="i need a full https:// url to fetch.")

        action_id = await approval.open_approval(
            session_id=uuid.UUID(session_id),
            domain="actions",
            tool="web.fetch",
            description=f"{method} {url[:80]}",
            payload={"url": url, "method": method},
            requires_approval=True,
        )
        return AgentResult(
            text=f"i'll {method.lower()} `{url}` and bring back what it says.",
            actions_opened=[str(action_id)],
            tool_calls=[{
                "tool": "web.draft",
                "args": {},
                "result": {"url": url, "method": method},
            }],
        )

    # ----- planner -----

    async def _plan(self, text: str) -> dict[str, Any]:
        try:
            mcp_tools = ""
            try:
                from api.integrations import mcp_host
                if mcp_host.configured():
                    mcp_tools = mcp_host.compact_tool_list(await mcp_host.list_all_tools())
            except Exception:
                mcp_tools = "(mcp lookup failed)"
            raw = await self._ask(
                system=INTENT_PROMPT.replace("{mcp_tools}", mcp_tools or "(none)"),
                messages=[{"role": "user", "content": text}],
                model=settings.model_default,
                max_tokens=400,
                temperature=0.0,
            )
            if raw.startswith("```"):
                raw = raw.strip("`")
                if raw.lower().startswith("json"):
                    raw = raw[4:]
            return json.loads(raw)
        except Exception as e:
            log.warning("actions plan parse failed", error=str(e))
            return {"tool": "none"}


actions_agent = ActionsAgent(name="actions", system_prompt="")
