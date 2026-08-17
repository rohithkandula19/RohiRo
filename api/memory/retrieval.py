"""multi-strategy retrieval with reciprocal rank fusion.

four retrieval strategies are run in parallel, each producing a ranked list:

  1. bm25 over conversations         (postgres tsvector)
  2. vector cosine over conversations
  3. trigram over tree_nodes         (memory tree summaries)
  4. bm25 over raw_events            (granular events the tree summarizes)

then RRF (Cormack et al 2009): rrf(item) = sum_i 1 / (k + rank_i)
items that show up in multiple strategies bubble to the top.

on top of RRF: a small recency boost (events from the last 24h count slightly
more), and the always-on "today's brief" tree node which is injected
unconditionally for temporal queries.
"""

from __future__ import annotations

import re
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Awaitable

from api.memory import entities as entities_mod
from api.memory.db import db
from api.memory.embeddings import embed
from api.memory.tree import engine as tree_engine
from api.observability.logging import log

RRF_K = 60                       # standard rrf constant; reduces effect of low-ranked items
PER_STRATEGY_CAP = 30            # how many items each strategy contributes
FINAL_CAP = 8                    # max items returned to the caller
RECENCY_HALF_LIFE_S = 14 * 86400 # two-week half life for the recency nudge


async def retrieve_relevant(query: str, *, limit: int = FINAL_CAP) -> list[dict[str, Any]]:
    if not query.strip():
        return []

    # 1. always-on: today/this_week brief if the query is temporal
    pinned: list[dict[str, Any]] = []
    period = _infer_period(query)
    if period:
        node = await tree_engine.get_brief(period=period)
        if node:
            pinned.append(_tree_to_ctx(node, label=f"brief · {period}", pinned=True))

    # 1b. always-on: if the query mentions a known entity, pin its profile
    for term in _query_terms(query):
        if len(term) < 3:
            continue
        try:
            prof = await entities_mod.entity_profile(term)
        except Exception:
            prof = None
        if prof:
            pinned.append(_entity_to_ctx(prof))
            break  # one entity is enough; don't bloat the prompt

    # 2. run all strategies in parallel-ish (postgres handles the concurrency)
    try:
        emb = await embed(query)
    except Exception as e:
        log.warning("retrieval embedding failed", error=str(e))
        emb = None

    strategies: dict[str, list[dict[str, Any]]] = {}
    strategies["convo_bm25"] = await _convo_bm25(query, PER_STRATEGY_CAP)
    if emb is not None:
        strategies["convo_vec"] = await _convo_vec(emb, PER_STRATEGY_CAP)
    if _has_topic_signal(query):
        strategies["tree_search"] = await _tree_search(query, PER_STRATEGY_CAP)
        strategies["events_bm25"] = await _events_bm25(query, PER_STRATEGY_CAP)

    # 3. fuse
    fused = _rrf(strategies, k=RRF_K)

    # 4. recency boost (small but real)
    fused = _apply_recency_boost(fused)

    # 5. polish: dedup tree lineage, cap per-source for diversity, drop empties
    fused = _dedup_tree_lineage(fused)
    fused = _drop_empty(fused)

    # 6. cap, dedup against pinned, source-balance, return
    pinned_ids = {(p["source"], p["id"]) for p in pinned}
    per_source_cap = 3
    per_source_count: dict[str, int] = {}
    out: list[dict[str, Any]] = []
    for item in fused:
        if (item["source"], item["id"]) in pinned_ids:
            continue
        src = item["source"]
        if per_source_count.get(src, 0) >= per_source_cap:
            continue
        per_source_count[src] = per_source_count.get(src, 0) + 1
        out.append(item)
        if len(out) >= max(0, limit - len(pinned)):
            break

    return pinned + out


# ----- strategies -----


def _vault_visible() -> bool:
    """vault rows are visible only from the vault lane. the taint follows
    the data: a cloud-bound prompt can never be assembled from vault rows."""
    from api.observability import lanes
    return lanes.get_lane() == "vault"


async def _convo_bm25(query: str, cap: int) -> list[dict[str, Any]]:
    rows = await db.fetch(
        """select id::text as id, body, created_at,
                  ts_rank(body_tsv, plainto_tsquery('english', $1)) as score
           from conversations
           where body_tsv @@ plainto_tsquery('english', $1)
             and (not vault or $3)
           order by score desc, created_at desc
           limit $2""",
        query, cap, _vault_visible(),
    )
    return [_to_item("conversation", r) for r in rows]


async def _convo_vec(emb: list[float], cap: int) -> list[dict[str, Any]]:
    rows = await db.fetch(
        """select id::text as id, body, created_at,
                  1 - (embedding <=> $1::vector) as score
           from conversations
           where embedding is not null
             and (not vault or $3)
           order by embedding <=> $1::vector
           limit $2""",
        emb, cap, _vault_visible(),
    )
    return [_to_item("conversation", r) for r in rows]


async def _tree_search(query: str, cap: int) -> list[dict[str, Any]]:
    terms = _query_terms(query)
    if not terms:
        return []
    patterns = [f"%{t}%" for t in terms]
    rows = await db.fetch(
        """select path as id, title, summary_md, depth, starts_at, ends_at,
                  greatest(similarity(summary_md, $1), 0.0) as score
           from tree_nodes
           where summary_md ilike any($2::text[])
              or title ilike any($2::text[])
           order by score desc, starts_at desc
           limit $3""",
        query, patterns, cap,
    )
    out = []
    for r in rows:
        out.append({
            "source": "memory_tree",
            "id": r["id"],
            "body": f"# {r['title']}\n{r['summary_md']}",
            "created_at": r["starts_at"],
            "score": float(r["score"] or 0),
            "label": f"timeline · {r['title']}",
            "depth": r["depth"],
        })
    return out


async def _events_bm25(query: str, cap: int) -> list[dict[str, Any]]:
    """multi-term ilike on raw_events.summary, scored by similarity when present."""
    terms = _query_terms(query)
    if not terms:
        return []
    patterns = [f"%{t}%" for t in terms]
    rows = await db.fetch(
        """select id::text as id, summary as body, happened_at as created_at, source as kind,
                  greatest(similarity(summary, $1), 0.0) as score
           from raw_events
           where summary ilike any($2::text[])
           order by score desc, happened_at desc
           limit $3""",
        query, patterns, cap,
    )
    out = []
    for r in rows:
        out.append({
            "source": f"event:{r['kind']}",
            "id": r["id"],
            "body": r["body"],
            "created_at": r["created_at"],
            "score": float(r["score"] or 0),
        })
    return out


def _query_terms(q: str) -> list[str]:
    """signal tokens for substring search. tokens > 2 chars, non-stopword."""
    stripped = re.sub(r"[^a-z0-9 ]", " ", q.lower())
    stop = {
        "the", "and", "for", "with", "any", "what", "who", "did", "was",
        "are", "from", "have", "had", "you", "ro", "let", "tell", "give",
        "about", "this", "that", "today", "tonight", "yesterday", "week",
        "month", "year", "happened", "summarize", "show", "find", "doing",
        "working",
    }
    tokens = [t for t in stripped.split() if len(t) > 2 and t not in stop]
    # de-dup preserving order
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out[:5]


# ----- fusion -----


def _rrf(strategies: dict[str, list[dict[str, Any]]], *, k: int = RRF_K) -> list[dict[str, Any]]:
    """reciprocal rank fusion. item key = (source, id)."""
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for strat_name, items in strategies.items():
        for rank, it in enumerate(items):  # rank starts at 0
            key = (it["source"], str(it["id"]))
            contrib = 1.0 / (k + rank + 1)
            if key not in seen:
                base = dict(it)
                base["rrf_score"] = 0.0
                base["matched_strategies"] = []
                seen[key] = base
            seen[key]["rrf_score"] += contrib
            seen[key]["matched_strategies"].append(strat_name)
    items = list(seen.values())
    items.sort(key=lambda x: x["rrf_score"], reverse=True)
    return items


def _dedup_tree_lineage(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """when multiple tree nodes from the same lineage match, keep only the deepest.

    /2026/05/13/14 contains everything /2026/05/13 and /2026/05 and /2026 and /
    contain (those are summaries of it). show the leaf, drop ancestors.

    runs only over `memory_tree` items; other sources untouched.
    """
    tree_items = [i for i in items if i.get("source") == "memory_tree"]
    other_items = [i for i in items if i.get("source") != "memory_tree"]
    if len(tree_items) < 2:
        return items

    # deepest first
    tree_items.sort(key=lambda h: -(h.get("depth") or 0))
    kept: list[dict[str, Any]] = []
    kept_paths: list[str] = []
    for h in tree_items:
        path = h["id"]
        # if any already-kept path is a descendant of this one, this is a redundant ancestor
        is_ancestor = any(
            (kp == path) or (path != "/" and kp.startswith(path + "/")) or (path == "/" and kp != "/")
            for kp in kept_paths
        )
        if is_ancestor:
            continue
        kept.append(h)
        kept_paths.append(path)

    # reassemble preserving the original (rrf-sorted) order
    keep_keys = {(h["source"], str(h["id"])) for h in kept}
    out: list[dict[str, Any]] = []
    for h in items:
        if h.get("source") == "memory_tree":
            if (h["source"], str(h["id"])) in keep_keys:
                out.append(h)
        else:
            out.append(h)
    return out


def _drop_empty(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """drop hits whose body is empty / a fallback marker / too short to be useful."""
    out = []
    for h in items:
        body = (h.get("body") or "").strip()
        if not body:
            continue
        if len(body) < 8:
            continue
        if body.startswith("[binary file"):
            continue
        out.append(h)
    return out


def _apply_recency_boost(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """nudge recent items up. small effect — rrf does most of the work."""
    now = datetime.now(tz=timezone.utc)
    for it in items:
        ts = it.get("created_at")
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                ts = None
        if not isinstance(ts, datetime):
            continue
        age = (now - (ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc))).total_seconds()
        recency = max(0.0, 2 ** (-age / RECENCY_HALF_LIFE_S))
        it["rrf_score"] += 0.02 * recency   # at most ~+0.02
    items.sort(key=lambda x: x["rrf_score"], reverse=True)
    return items


# ----- helpers / temporal -----


_TEMPORAL_PATTERNS = (
    "today", "yesterday", "this week", "last week", "this month", "last month",
    "this year", "last year", "recently", "this morning", "tonight",
    "what did i", "what happened", "summarize my", "summarize this",
    "what was i working on",
)


def _infer_period(q: str) -> str | None:
    s = q.lower()
    if "yesterday" in s:
        return "yesterday"
    if "last week" in s or "this week" in s:
        return "this_week"
    if "last month" in s or "this month" in s:
        return "this_month"
    if "last year" in s or "this year" in s:
        return "this_year"
    if "today" in s or "this morning" in s or "tonight" in s:
        return "today"
    if any(p in s for p in _TEMPORAL_PATTERNS):
        return "today"
    return None


def _has_topic_signal(q: str) -> bool:
    """is there a noun/topic beyond temporal words? cheap heuristic."""
    stripped = q.lower()
    for p in _TEMPORAL_PATTERNS:
        stripped = stripped.replace(p, " ")
    stripped = re.sub(r"[^a-z0-9 ]", " ", stripped)
    tokens = [t for t in stripped.split() if len(t) > 2]
    stop = {"the", "and", "for", "with", "any", "what", "who", "did", "was",
            "are", "from", "have", "had", "you", "ro", "let", "tell", "give"}
    nouns = [t for t in tokens if t not in stop]
    return len(nouns) >= 1


def _entity_to_ctx(prof: dict[str, Any]) -> dict[str, Any]:
    events = prof.get("recent_events") or []
    bullets = "\n".join(
        f"- [{e.get('source','?')}/{e.get('kind','?')}] {e.get('summary','')[:140]}"
        for e in events[:6]
    )
    body = (
        f"# {prof.get('name','?')} ({prof.get('kind','?')})\n"
        f"seen {prof.get('seen_count', 1)}x · last "
        f"{(prof.get('last_seen_at','') or '')[:16].replace('T',' ')}\n\n"
        f"{bullets}"
    )
    return {
        "source": "entity",
        "id": prof.get("id", ""),
        "body": body,
        "created_at": prof.get("last_seen_at"),
        "score": 1.0,
        "rrf_score": 999.0,
        "label": f"who · {prof.get('name','?')}",
        "pinned": True,
    }


def _tree_to_ctx(node: Any, *, label: str, pinned: bool = False) -> dict[str, Any]:
    data = asdict(node) if is_dataclass(node) else dict(node)
    return {
        "source": "memory_tree",
        "id": data["path"],
        "body": f"# {data.get('title','')}\n{data.get('summary_md','')}",
        "created_at": data.get("starts_at"),
        "score": 1.0,
        "rrf_score": 999.0 if pinned else 0.0,
        "label": label,
        "depth": data.get("depth"),
        "pinned": pinned,
    }


def _to_item(source: str, r: Any) -> dict[str, Any]:
    return {
        "source": source,
        "id": r["id"],
        "body": r["body"],
        "created_at": r["created_at"],
        "score": float(r["score"] or 0),
    }


# ----- legacy helpers kept for callers -----


async def get_profile_body() -> str:
    row = await db.fetchrow("select body from profile where id = 1")
    return row["body"] if row else ""


async def recent_decisions(days: int = 30, limit: int = 10) -> list[dict[str, Any]]:
    since = datetime.now(tz=timezone.utc) - timedelta(days=days)
    rows = await db.fetch(
        "select id::text, title, body, decided_at from decisions "
        "where decided_at >= $1 order by decided_at desc limit $2",
        since, limit,
    )
    return [dict(r) for r in rows]
