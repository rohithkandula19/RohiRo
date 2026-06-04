"""linear (linear.app) client — GraphQL.

uses a personal API key from keychain (`linear_token`).
get one at: linear.app → settings → account → security & access → personal API keys.

verbs:
- configured()
- list_my_issues(status='active', limit=25)       -> list[Issue]
- search_issues(query, limit=15)                   -> list[Issue]
- get_issue(identifier)                            -> Issue   (identifier = 'RO-42' or uuid)
- list_my_projects(limit=20)                       -> list[Project]
- create_issue(team_key, title, description?, priority?)  -> dict   [approval]
- add_comment(issue_id_or_identifier, body)               -> dict   [approval]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from api.config import secrets
from api.observability.logging import log

API = "https://api.linear.app/graphql"


@dataclass
class Issue:
    id: str
    identifier: str         # "RO-42"
    title: str
    state: str              # "Triage" | "In Progress" | "Done" | ...
    priority: int           # 0=no, 1=urgent, 2=high, 3=medium, 4=low
    url: str
    assignee: str = ""
    team: str = ""
    project: str = ""
    description: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Project:
    id: str
    name: str
    state: str
    url: str
    description: str = ""


def configured() -> bool:
    return bool(secrets.get("linear_token"))


def _headers() -> dict[str, str]:
    token = secrets.get("linear_token")
    if not token:
        raise RuntimeError(
            "linear not configured. create a personal API key at "
            "linear.app → settings → account → security & access → personal API keys, "
            "then `keyring set ro linear_token`."
        )
    return {"Authorization": token, "Content-Type": "application/json"}


async def _gql(query: str, variables: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.post(API, headers=_headers(), json={"query": query, "variables": variables or {}})
        if r.status_code != 200:
            raise RuntimeError(f"linear graphql {r.status_code}: {r.text[:300]}")
        data = r.json()
        if data.get("errors"):
            raise RuntimeError(f"linear graphql error: {data['errors']}")
        return data.get("data") or {}


# ----- read -----


_ISSUE_FIELDS = """
  id identifier title priority createdAt updatedAt url
  state { name type }
  assignee { name }
  team { name key }
  project { name }
  description
"""


def _to_issue(x: dict[str, Any]) -> Issue:
    return Issue(
        id=x["id"],
        identifier=x.get("identifier", ""),
        title=x.get("title", ""),
        state=(x.get("state") or {}).get("name", ""),
        priority=int(x.get("priority") or 0),
        url=x.get("url", ""),
        assignee=(x.get("assignee") or {}).get("name", "") or "",
        team=(x.get("team") or {}).get("name", "") or "",
        project=(x.get("project") or {}).get("name", "") or "",
        description=(x.get("description") or "")[:1000],
        created_at=x.get("createdAt", ""),
        updated_at=x.get("updatedAt", ""),
    )


async def list_my_issues(status: str = "active", limit: int = 25) -> list[Issue]:
    """status: 'active' (started+todo+triage) | 'all' | 'completed'."""
    q = """
    query MyIssues($first: Int!) {
      viewer { id }
      issues(
        first: $first,
        filter: { assignee: { isMe: { eq: true } } },
        orderBy: updatedAt
      ) {
        nodes { %s }
      }
    }
    """ % _ISSUE_FIELDS
    data = await _gql(q, {"first": limit * 2})
    nodes = data.get("issues", {}).get("nodes", []) or []
    out = [_to_issue(n) for n in nodes]
    if status == "completed":
        out = [i for i in out if (i.state or "").lower() in {"done", "completed", "cancelled", "canceled", "closed"}]
    elif status != "all":  # active
        out = [i for i in out if (i.state or "").lower() not in {"done", "completed", "cancelled", "canceled", "closed"}]
    return out[:limit]


async def search_issues(query: str, limit: int = 15) -> list[Issue]:
    q = """
    query Search($q: String!, $first: Int!) {
      issueSearch(query: $q, first: $first) {
        nodes { %s }
      }
    }
    """ % _ISSUE_FIELDS
    try:
        data = await _gql(q, {"q": query, "first": limit})
        nodes = data.get("issueSearch", {}).get("nodes", []) or []
        return [_to_issue(n) for n in nodes]
    except Exception:
        # older API versions use `issues(filter: {title: {contains: ...}})`; fall back
        q2 = """
        query Search2($first: Int!, $q: String!) {
          issues(first: $first, filter: { title: { containsIgnoreCase: $q } }) {
            nodes { %s }
          }
        }
        """ % _ISSUE_FIELDS
        data = await _gql(q2, {"q": query, "first": limit})
        nodes = data.get("issues", {}).get("nodes", []) or []
        return [_to_issue(n) for n in nodes]


async def get_issue(identifier: str) -> Optional[Issue]:
    q = """
    query GetIssue($id: String!) {
      issue(id: $id) { %s }
    }
    """ % _ISSUE_FIELDS
    data = await _gql(q, {"id": identifier})
    node = data.get("issue")
    return _to_issue(node) if node else None


async def list_my_projects(limit: int = 20) -> list[Project]:
    q = """
    query Projects($first: Int!) {
      projects(first: $first, orderBy: updatedAt) {
        nodes { id name state url description }
      }
    }
    """
    data = await _gql(q, {"first": limit})
    nodes = data.get("projects", {}).get("nodes", []) or []
    return [
        Project(
            id=n["id"], name=n.get("name", ""),
            state=n.get("state", ""), url=n.get("url", ""),
            description=(n.get("description") or "")[:300],
        )
        for n in nodes
    ]


# ----- write (approval-gated) -----


async def create_issue(
    *, team_key: str, title: str, description: str = "", priority: int = 0,
) -> dict[str, Any]:
    """create an issue. team_key like 'RO' (the prefix of identifiers)."""
    # resolve team key to team id
    teams = await _gql("query { teams { nodes { id key name } } }")
    nodes = teams.get("teams", {}).get("nodes", []) or []
    team = next((t for t in nodes if t["key"].upper() == team_key.upper()), None)
    if not team:
        raise RuntimeError(f"no team with key '{team_key}'. found: {[t['key'] for t in nodes]}")

    m = """
    mutation Create($input: IssueCreateInput!) {
      issueCreate(input: $input) {
        success
        issue { id identifier title url state { name } }
      }
    }
    """
    data = await _gql(m, {
        "input": {
            "teamId": team["id"],
            "title": title,
            "description": description or "",
            "priority": priority,
        },
    })
    res = data.get("issueCreate") or {}
    if not res.get("success"):
        raise RuntimeError(f"linear create failed: {res}")
    issue = res.get("issue") or {}
    return {
        "id": issue.get("id"),
        "identifier": issue.get("identifier"),
        "title": issue.get("title"),
        "url": issue.get("url"),
        "state": (issue.get("state") or {}).get("name", ""),
    }


async def add_comment(issue_identifier: str, body: str) -> dict[str, Any]:
    # resolve identifier to id
    ish = await get_issue(issue_identifier)
    if not ish:
        raise RuntimeError(f"no issue matching '{issue_identifier}'")
    m = """
    mutation Comment($input: CommentCreateInput!) {
      commentCreate(input: $input) {
        success
        comment { id url }
      }
    }
    """
    data = await _gql(m, {"input": {"issueId": ish.id, "body": body}})
    res = data.get("commentCreate") or {}
    if not res.get("success"):
        raise RuntimeError(f"linear comment failed: {res}")
    c = res.get("comment") or {}
    return {"comment_id": c.get("id"), "url": c.get("url"), "issue": ish.identifier}
