"""code sub-agent — github wired.

intents:
- list_repos     ("show my repos", "what am i working on")
- list_prs       ("any open PRs", "show prs on rohflow")
- summarize      ("summarize rohflow", "what changed in <repo> this week")
- recent_commits ("recent commits on rohflow")
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from typing import Any, Optional

from api.agents.base import Agent, AgentResult
from api.config import settings
from api.integrations import github
from api.observability.logging import log

INTENT_PROMPT = """classify a request about code/github into one intent and extract params.

intents:
- "list_repos": user wants to see their repositories
- "list_prs": user wants pull requests (open prs, my prs)
- "summarize": user wants a summary of a repo (what changed, what's new, summarize X)
- "recent_commits": user wants recent commits on a specific repo
- "other": none of the above

params:
- "repo": "owner/repo" if mentioned, else short name (e.g. "rohflow"), else ""

reply with json only:
{"intent": "...", "repo": "..."}"""


class CodeAgent(Agent):
    async def run(self, *, session_id: str, user_text: str, context: dict[str, Any]) -> AgentResult:
        if not github.configured():
            return AgentResult(
                text=(
                    "i can't reach github yet — your token isn't set.\n\n"
                    "one-time setup:\n"
                    "  1. https://github.com/settings/tokens?type=beta — create a fine-grained PAT\n"
                    "  2. scopes: read access to your repos + read user\n"
                    "  3. run `keyring set ro github_token` and paste the token\n"
                ),
                error="github_not_configured",
            )

        intent = await self._classify_intent(user_text)
        kind = intent.get("intent", "other")
        repo = intent.get("repo", "")

        if kind == "list_repos" or (kind == "other" and not repo):
            return await self._list_repos()
        if kind == "list_prs":
            return await self._list_prs(repo)
        if kind == "summarize":
            return await self._summarize(repo)
        if kind == "recent_commits":
            return await self._recent_commits(repo)

        return await self._list_repos()

    async def _list_repos(self) -> AgentResult:
        try:
            repos = await github.list_my_repos(limit=12)
        except Exception as e:
            return AgentResult(text=f"github request failed. {e}", error=str(e))

        if not repos:
            return AgentResult(text="no repos visible with this token.")

        lines = [f"{len(repos)} recent repos:"]
        for r in repos:
            tag = " (private)" if r.private else ""
            lines.append(f"• {r.full_name}{tag}  —  {r.description or '(no description)'}")
        return AgentResult(
            text="\n".join(lines),
            tool_calls=[{"tool": "github.list_repos", "args": {}, "result": [asdict(r) for r in repos]}],
        )

    async def _list_prs(self, repo: str) -> AgentResult:
        repo_full = await self._resolve_repo(repo) if repo else None
        try:
            prs = await github.list_open_prs(repo=repo_full)
        except Exception as e:
            return AgentResult(text=f"github request failed. {e}", error=str(e))

        if not prs:
            return AgentResult(text=f"no open PRs{' on ' + repo_full if repo_full else ''}.")

        lines = [f"{len(prs)} open PR{'s' if len(prs) != 1 else ''}:"]
        for p in prs:
            tag = " [draft]" if p.draft else ""
            lines.append(f"• {p.repo}#{p.number} — {p.title[:80]}{tag} (by {p.author})")
        return AgentResult(
            text="\n".join(lines),
            tool_calls=[{"tool": "github.list_prs", "args": {"repo": repo_full}, "result": [asdict(p) for p in prs]}],
        )

    async def _summarize(self, repo: str) -> AgentResult:
        repo_full = await self._resolve_repo(repo)
        if not repo_full:
            return AgentResult(text="which repo? try `summarize rohflow` or give me owner/repo.")
        try:
            summary = await github.get_repo_summary(repo_full)
        except Exception as e:
            return AgentResult(text=f"github request failed. {e}", error=str(e))

        commits = summary["recent_commits"]
        if commits:
            # let claude write a human summary of the recent commits
            commit_lines = "\n".join(f"- {c['short_sha']} {c['author']}: {c['message']}" for c in commits)
            sys = "summarize what's been happening in this repo. 2-3 sentences, plain english."
            user = (
                f"repo: {repo_full}\n"
                f"description: {summary['description']}\n"
                f"recent commits:\n{commit_lines}\n"
            )
            try:
                blurb = await self._ask(
                    system=sys,
                    messages=[{"role": "user", "content": user}],
                    model=settings.model_default,
                    max_tokens=300,
                    temperature=0.5,
                )
            except Exception:
                blurb = ""
        else:
            blurb = "no recent commits."

        text = (
            f"**{repo_full}**\n"
            f"{summary['description'] or '(no description)'}\n\n"
            f"{summary['open_prs']} open PRs · {summary['open_issues']} issues · {summary['language']}\n\n"
            f"{blurb}"
        )
        return AgentResult(
            text=text,
            tool_calls=[{"tool": "github.summary", "args": {"repo": repo_full}, "result": summary}],
        )

    async def _recent_commits(self, repo: str) -> AgentResult:
        repo_full = await self._resolve_repo(repo)
        if not repo_full:
            return AgentResult(text="which repo? give me owner/repo or a unique name.")
        try:
            commits = await github.list_recent_commits(repo_full, limit=10)
        except Exception as e:
            return AgentResult(text=f"github request failed. {e}", error=str(e))

        if not commits:
            return AgentResult(text=f"no commits found on {repo_full}.")

        lines = [f"recent commits on {repo_full}:"]
        for c in commits:
            lines.append(f"• {c.short_sha} {c.author}: {c.message[:80]}")
        return AgentResult(
            text="\n".join(lines),
            tool_calls=[{"tool": "github.commits", "args": {"repo": repo_full}, "result": [asdict(c) for c in commits]}],
        )

    # ----- helpers -----

    async def _resolve_repo(self, hint: str) -> Optional[str]:
        if not hint:
            return None
        if "/" in hint:
            return hint
        # match by name from the user's repos
        try:
            repos = await github.list_my_repos(limit=50)
        except Exception:
            return None
        h = hint.lower()
        for r in repos:
            if r.name.lower() == h:
                return r.full_name
        # fuzzy contains
        for r in repos:
            if h in r.name.lower():
                return r.full_name
        return None

    async def _classify_intent(self, text: str) -> dict[str, Any]:
        try:
            raw = await self._ask(
                system=INTENT_PROMPT,
                messages=[{"role": "user", "content": text}],
                model=settings.model_cheap,
                max_tokens=120,
                temperature=0.0,
            )
            if raw.startswith("```"):
                raw = raw.strip("`")
                if raw.lower().startswith("json"):
                    raw = raw[4:]
            return json.loads(raw)
        except Exception:
            return {"intent": "other", "repo": ""}


code_agent = CodeAgent(name="code", system_prompt="")
