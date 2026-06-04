"""memory tree engine.

write_event       -> append a raw_event row (called by agents/auto-fetch hooks)
summarize_pending -> roll up unsummarized events into hour leaves, propagate up
get_brief         -> read the day/week/month summary
search            -> trigram search over node summaries
walk_recent       -> recent hour leaves as plain rows

token budget is small per call: claude-haiku is fine.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from api.config import settings
from api.memory.db import db
from api.memory.tree import vault
from api.observability.claude import claude_client
from api.observability.logging import log

# ----- write -----


async def write_event(
    *,
    source: str,
    kind: str,
    summary: str,
    payload: Optional[dict[str, Any]] = None,
    actor: str = "ro",
    when: Optional[datetime] = None,
) -> str:
    """append a raw event. cheap. agents/integrations call this freely."""
    happened_at = when or datetime.now(tz=timezone.utc)
    row = await db.fetchrow(
        """insert into raw_events (happened_at, source, kind, actor, summary, payload)
           values ($1, $2, $3, $4, $5, $6) returning id::text""",
        happened_at,
        source,
        kind,
        actor,
        summary[:500],
        json.dumps(payload or {}),
    )
    return row["id"]


# ----- summarize -----


async def summarize_pending(*, limit_hours: int = 24) -> dict[str, Any]:
    """walk the pending_hours view, write/refresh each hour-leaf, propagate up.

    cheap to run frequently. when nothing's pending, returns counts=0.
    """
    rows = await db.fetch(
        "select path, event_count, starts_at from pending_hours "
        "order by starts_at desc limit $1",
        limit_hours,
    )
    if not rows:
        return {"hours_processed": 0, "ancestors_refreshed": 0}

    hours_done = 0
    dirty_paths: set[str] = set()
    for r in rows:
        path = r["path"]
        await _summarize_hour(path)
        hours_done += 1
        dirty_paths.update(_ancestor_paths(path))

    # bottom-up: refresh ancestors deepest-first (day -> month -> year -> root)
    for d in (3, 2, 1, 0):
        for p in sorted([p for p in dirty_paths if _depth_of(p) == d]):
            await _summarize_ancestor(p)

    return {"hours_processed": hours_done, "ancestors_refreshed": len(dirty_paths)}


async def _summarize_hour(path: str) -> None:
    """summarize all unsummarized events whose hour bucket = path."""
    # path looks like /2026/05/13/14
    year, month, day, hour = _parse_path(path)
    start = datetime(year, month, day, hour, 0, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=1)

    events = await db.fetch(
        """select id, happened_at, source, kind, actor, summary, payload
           from raw_events
           where happened_at >= $1 and happened_at < $2 and summarized_at is null
           order by happened_at""",
        start, end,
    )
    if not events:
        return

    lines = [
        f"- [{e['source']}/{e['kind']}] {e['summary']}"
        for e in events
    ]
    bullet_block = "\n".join(lines)

    sys = (
        "you summarize one hour of ro's day. output 2-5 sentence prose paragraph + "
        "a compact bullet list of distinct things that happened. no fluff, no markdown headings."
    )
    user = (
        f"hour: {start.isoformat()}\n"
        f"events ({len(events)}):\n{bullet_block}\n\n"
        f"summarize."
    )

    try:
        resp = await claude_client.message(
            model=settings.model_cheap,
            system=sys,
            messages=[{"role": "user", "content": user}],
            max_tokens=400,
            temperature=0.3,
        )
        summary_md = "".join(b.text for b in resp.content if b.type == "text").strip()
    except Exception as e:
        log.exception("tree: hour summarize failed", path=path)
        summary_md = bullet_block  # fallback: raw bullets

    title = start.strftime("%I %p").lstrip("0").lower()
    await _upsert_node(
        path=path, depth=4, starts_at=start, ends_at=end,
        summary_md=summary_md, title=title, event_count=len(events),
    )
    # mark all as summarized
    ids = [e["id"] for e in events]
    await db.execute(
        "update raw_events set summarized_at = now() where id = any($1::uuid[])",
        ids,
    )

    # mark all ancestors dirty
    for anc in _ancestor_paths(path):
        await db.execute(
            "update tree_nodes set children_dirty = true where path = $1",
            anc,
        )

    # also write to obsidian vault for human browsing
    try:
        vault.write_hour(path, start, summary_md, [dict(e) for e in events])
    except Exception:
        log.warning("vault write failed", path=path)


async def _summarize_ancestor(path: str) -> None:
    """given /yyyy or /yyyy/mm or /yyyy/mm/dd, summarize from immediate children."""
    if path == "/":
        # root: just refresh from years
        kids = await db.fetch(
            "select path, summary_md, event_count, title from tree_nodes "
            "where depth = 1 order by starts_at desc"
        )
        starts_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        ends_at = datetime(2100, 1, 1, tzinfo=timezone.utc)
        title = "everything"
    else:
        depth = _depth_of(path)
        prefix = path + "/"
        kids = await db.fetch(
            "select path, summary_md, event_count, title, starts_at, ends_at "
            "from tree_nodes "
            "where depth = $1 and path like $2 "
            "order by starts_at desc",
            depth + 1, prefix + "%",
        )
        if not kids:
            return
        starts_at = min(k["starts_at"] for k in kids)
        ends_at = max(k["ends_at"] for k in kids)
        depth_label = {1: "year", 2: "month", 3: "day"}[depth]
        title = _format_title(path, depth_label, starts_at)

    if not kids:
        return

    blocks = []
    for k in kids[:24]:  # cap to keep token budget sane
        blocks.append(f"## {k['title']} ({k['event_count']} events)\n{k['summary_md']}")
    joined = "\n\n".join(blocks)

    sys = (
        "you summarize ro's life at one level of the timeline (day, month, or year). "
        "output a tight 4-8 sentence narrative + a short bullet list of the most important "
        "themes (people, projects, decisions). no fluff. focus on what changed and what's now true."
    )
    user = f"period: {starts_at.isoformat()} → {ends_at.isoformat()}\n\nchild summaries:\n\n{joined}\n\nroll up."

    try:
        resp = await claude_client.message(
            model=settings.model_cheap,
            system=sys,
            messages=[{"role": "user", "content": user}],
            max_tokens=700,
            temperature=0.3,
        )
        summary_md = "".join(b.text for b in resp.content if b.type == "text").strip()
    except Exception:
        log.exception("tree: ancestor summarize failed", path=path)
        summary_md = "\n\n".join(f"### {k['title']}\n{k['summary_md']}" for k in kids[:6])

    total_events = sum(k["event_count"] for k in kids)
    depth = _depth_of(path)
    await _upsert_node(
        path=path or "/", depth=depth, starts_at=starts_at, ends_at=ends_at,
        summary_md=summary_md, title=title, event_count=total_events,
    )
    await db.execute(
        "update tree_nodes set children_dirty = false where path = $1",
        path,
    )


# ----- read -----


@dataclass
class TreeNode:
    path: str
    depth: int
    title: str
    summary_md: str
    starts_at: str
    ends_at: str
    event_count: int


async def get_brief(period: str = "today") -> Optional[TreeNode]:
    """grab a single node's summary.

    period: today | yesterday | this_week | this_month | this_year | <iso-date>
    """
    now = datetime.now(tz=timezone.utc)
    if period == "today":
        path = _path_for(now, 3)
    elif period == "yesterday":
        path = _path_for(now - timedelta(days=1), 3)
    elif period in ("this_week", "this_month"):
        path = _path_for(now, 2)
    elif period == "this_year":
        path = _path_for(now, 1)
    else:
        try:
            d = datetime.fromisoformat(period)
            path = _path_for(d, 3)
        except Exception:
            path = _path_for(now, 3)

    row = await db.fetchrow(
        "select path, depth, title, summary_md, starts_at, ends_at, event_count "
        "from tree_nodes where path = $1",
        path,
    )
    if not row:
        return None
    return TreeNode(
        path=row["path"], depth=row["depth"], title=row["title"],
        summary_md=row["summary_md"],
        starts_at=row["starts_at"].isoformat(),
        ends_at=row["ends_at"].isoformat(),
        event_count=row["event_count"],
    )


async def search(query: str, limit: int = 8) -> list[TreeNode]:
    """trigram + lexical search over summaries."""
    if not query.strip():
        return []
    rows = await db.fetch(
        """select path, depth, title, summary_md, starts_at, ends_at, event_count,
                  similarity(summary_md, $1) as score
           from tree_nodes
           where summary_md % $1
           order by score desc, starts_at desc
           limit $2""",
        query, limit,
    )
    return [
        TreeNode(
            path=r["path"], depth=r["depth"], title=r["title"],
            summary_md=r["summary_md"],
            starts_at=r["starts_at"].isoformat(),
            ends_at=r["ends_at"].isoformat(),
            event_count=r["event_count"],
        )
        for r in rows
    ]


async def walk_recent(depth: int = 3, limit: int = 14) -> list[TreeNode]:
    rows = await db.fetch(
        "select path, depth, title, summary_md, starts_at, ends_at, event_count "
        "from tree_nodes where depth = $1 order by starts_at desc limit $2",
        depth, limit,
    )
    return [
        TreeNode(
            path=r["path"], depth=r["depth"], title=r["title"],
            summary_md=r["summary_md"],
            starts_at=r["starts_at"].isoformat(),
            ends_at=r["ends_at"].isoformat(),
            event_count=r["event_count"],
        )
        for r in rows
    ]


# ----- helpers -----


async def _upsert_node(*, path: str, depth: int, starts_at: datetime, ends_at: datetime,
                       summary_md: str, title: str, event_count: int) -> None:
    await db.execute(
        """insert into tree_nodes (path, depth, starts_at, ends_at, summary_md, title, event_count, updated_at)
           values ($1, $2, $3, $4, $5, $6, $7, now())
           on conflict (path) do update set
             summary_md = excluded.summary_md,
             title = excluded.title,
             event_count = excluded.event_count,
             ends_at = excluded.ends_at,
             updated_at = now()""",
        path, depth, starts_at, ends_at, summary_md, title, event_count,
    )


def _depth_of(path: str) -> int:
    if path in ("", "/"):
        return 0
    return path.count("/")


def _parse_path(path: str) -> tuple[int, int, int, int]:
    """/yyyy/mm/dd/hh -> ints."""
    parts = [p for p in path.split("/") if p]
    while len(parts) < 4:
        parts.append("00")
    return int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])


def _path_for(dt: datetime, depth: int) -> str:
    if depth <= 0:
        return "/"
    parts = ["", f"{dt.year:04d}"]
    if depth >= 2:
        parts.append(f"{dt.month:02d}")
    if depth >= 3:
        parts.append(f"{dt.day:02d}")
    if depth >= 4:
        parts.append(f"{dt.hour:02d}")
    return "/".join(parts)


def _ancestor_paths(path: str) -> list[str]:
    """[/2026/05/13, /2026/05, /2026, /]"""
    parts = [p for p in path.split("/") if p]
    out = []
    for i in range(len(parts) - 1, -1, -1):
        if i == 0:
            out.append("/")
        else:
            out.append("/" + "/".join(parts[:i]))
    return out


def _format_title(path: str, depth_label: str, starts_at: datetime) -> str:
    if depth_label == "year":
        return f"{starts_at.year}"
    if depth_label == "month":
        return starts_at.strftime("%B %Y").lower()
    if depth_label == "day":
        return starts_at.strftime("%a %b %d").lower()
    return path
