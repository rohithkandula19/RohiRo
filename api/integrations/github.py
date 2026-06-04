"""github client.

uses a personal access token from keychain (`github_token`). httpx async,
no extra deps beyond what's already in the stack.

verbs:
- configured()
- list_my_repos(limit=10, sort='updated')      -> list[Repo]
- list_open_prs(repo? -> all-user if omitted)   -> list[PR]
- list_recent_commits(repo, branch='main', limit=10) -> list[Commit]
- get_repo_summary(repo)                        -> dict (counts + last commit + ci)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from api.config import secrets

API = "https://api.github.com"


@dataclass
class Repo:
    full_name: str          # "owner/repo"
    name: str
    description: str
    private: bool
    default_branch: str
    pushed_at: str
    open_issues: int
    stargazers: int
    language: str
    html_url: str


@dataclass
class PR:
    number: int
    repo: str               # "owner/repo"
    title: str
    state: str              # open | closed
    draft: bool
    author: str
    created_at: str
    updated_at: str
    url: str
    additions: int = 0
    deletions: int = 0


@dataclass
class Commit:
    sha: str
    short_sha: str
    repo: str
    author: str
    message: str
    url: str
    committed_at: str


def configured() -> bool:
    return bool(secrets.get("github_token"))


def _headers() -> dict[str, str]:
    token = secrets.get("github_token")
    if not token:
        raise RuntimeError(
            "github not configured. run `keyring set ro github_token` and paste a PAT "
            "with `repo` + `read:user` scopes."
        )
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ro-agent",
    }


async def list_my_repos(limit: int = 10, sort: str = "updated") -> list[Repo]:
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.get(
            f"{API}/user/repos",
            params={"sort": sort, "per_page": limit, "affiliation": "owner,collaborator"},
            headers=_headers(),
        )
        r.raise_for_status()
        return [_to_repo(x) for x in r.json()]


async def list_open_prs(repo: Optional[str] = None, limit: int = 20) -> list[PR]:
    async with httpx.AsyncClient(timeout=15.0) as c:
        if repo:
            r = await c.get(
                f"{API}/repos/{repo}/pulls",
                params={"state": "open", "per_page": limit},
                headers=_headers(),
            )
            r.raise_for_status()
            return [_to_pr(x, repo) for x in r.json()]

        # all open PRs across the user's repos: search api
        user = (await _whoami())["login"]
        r = await c.get(
            f"{API}/search/issues",
            params={
                "q": f"is:open is:pr author:{user}",
                "per_page": limit,
                "sort": "updated",
            },
            headers=_headers(),
        )
        r.raise_for_status()
        items = r.json().get("items", [])
        out: list[PR] = []
        for it in items:
            repo_full = it["repository_url"].split("/repos/")[-1]
            out.append(_to_pr(it, repo_full, from_search=True))
        return out


async def list_recent_commits(repo: str, branch: str = "main", limit: int = 10) -> list[Commit]:
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.get(
            f"{API}/repos/{repo}/commits",
            params={"sha": branch, "per_page": limit},
            headers=_headers(),
        )
        r.raise_for_status()
        items = r.json()
        out: list[Commit] = []
        for x in items:
            sha = x["sha"]
            out.append(Commit(
                sha=sha,
                short_sha=sha[:7],
                repo=repo,
                author=(x.get("author") or {}).get("login") or x["commit"]["author"]["name"],
                message=x["commit"]["message"].split("\n", 1)[0],
                url=x["html_url"],
                committed_at=x["commit"]["author"]["date"],
            ))
        return out


async def get_repo_summary(repo: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.get(f"{API}/repos/{repo}", headers=_headers())
        r.raise_for_status()
        info = r.json()
        commits = await list_recent_commits(repo, branch=info["default_branch"], limit=5)
        prs = await list_open_prs(repo=repo, limit=10)
        return {
            "repo": repo,
            "description": info.get("description") or "",
            "default_branch": info["default_branch"],
            "open_prs": len(prs),
            "open_issues": info.get("open_issues_count", 0),
            "stargazers": info.get("stargazers_count", 0),
            "language": info.get("language") or "",
            "pushed_at": info.get("pushed_at", ""),
            "recent_commits": [
                {"short_sha": c.short_sha, "author": c.author, "message": c.message, "at": c.committed_at}
                for c in commits
            ],
        }


async def _whoami() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.get(f"{API}/user", headers=_headers())
        r.raise_for_status()
        return r.json()


def _to_repo(x: dict[str, Any]) -> Repo:
    return Repo(
        full_name=x["full_name"],
        name=x["name"],
        description=x.get("description") or "",
        private=x.get("private", False),
        default_branch=x.get("default_branch", "main"),
        pushed_at=x.get("pushed_at", ""),
        open_issues=x.get("open_issues_count", 0),
        stargazers=x.get("stargazers_count", 0),
        language=x.get("language") or "",
        html_url=x.get("html_url", ""),
    )


def _to_pr(x: dict[str, Any], repo: str, *, from_search: bool = False) -> PR:
    if from_search:
        # search api uses 'user' instead of 'user.login' for author
        author = (x.get("user") or {}).get("login", "")
        return PR(
            number=x.get("number", 0),
            repo=repo,
            title=x.get("title", ""),
            state=x.get("state", "open"),
            draft=x.get("draft", False),
            author=author,
            created_at=x.get("created_at", ""),
            updated_at=x.get("updated_at", ""),
            url=x.get("html_url", ""),
        )
    return PR(
        number=x.get("number", 0),
        repo=repo,
        title=x.get("title", ""),
        state=x.get("state", "open"),
        draft=x.get("draft", False),
        author=(x.get("user") or {}).get("login", ""),
        created_at=x.get("created_at", ""),
        updated_at=x.get("updated_at", ""),
        url=x.get("html_url", ""),
        additions=x.get("additions", 0),
        deletions=x.get("deletions", 0),
    )
