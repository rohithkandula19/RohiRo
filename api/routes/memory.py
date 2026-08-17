"""memory routes. profile crud, contacts, decisions, conversation search."""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.memory import autofetch
from api.memory import entities as entities_mod
from api.memory.db import db
from api.memory.retrieval import retrieve_relevant
from api.memory.tree import engine as tree_engine

router = APIRouter()


class ProfileIn(BaseModel):
    body: str


class ProfileOut(BaseModel):
    body: str
    updated_at: str


class ContactIn(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    company: Optional[str] = None
    notes: Optional[str] = None


class DecisionIn(BaseModel):
    title: str
    body: str
    tags: list[str] = []


@router.get("/profile", response_model=ProfileOut)
async def get_profile() -> ProfileOut:
    row = await db.fetchrow("select body, updated_at from profile where id = 1")
    if not row:
        return ProfileOut(body="", updated_at="")
    return ProfileOut(body=row["body"], updated_at=row["updated_at"].isoformat())


@router.put("/profile", response_model=ProfileOut)
async def put_profile(payload: ProfileIn) -> ProfileOut:
    await db.execute("update profile set body = $1 where id = 1", payload.body)
    return await get_profile()


@router.get("/contacts")
async def list_contacts(q: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
    if q:
        rows = await db.fetch(
            """select id::text, name, email, phone, role, company, notes,
                       last_interaction_at, updated_at
               from contacts
               where name ilike $1 or email ilike $1 or company ilike $1
               order by coalesce(last_interaction_at, updated_at) desc
               limit $2""",
            f"%{q}%",
            limit,
        )
    else:
        rows = await db.fetch(
            """select id::text, name, email, phone, role, company, notes,
                       last_interaction_at, updated_at
               from contacts
               order by coalesce(last_interaction_at, updated_at) desc
               limit $1""",
            limit,
        )
    return [_serialize(r) for r in rows]


@router.post("/contacts")
async def add_contact(payload: ContactIn) -> dict[str, Any]:
    row = await db.fetchrow(
        """insert into contacts (name, email, phone, role, company, notes)
           values ($1, $2, $3, $4, $5, $6)
           returning id::text, name, email, phone, role, company, notes, updated_at""",
        payload.name,
        payload.email,
        payload.phone,
        payload.role,
        payload.company,
        payload.notes,
    )
    if not row:
        raise HTTPException(500, "insert failed")
    return _serialize(row)


@router.get("/archive/search")
async def archive_search(q: str, limit: int = 20) -> list[dict[str, Any]]:
    """total recall: search the lifetime corpus (fts, vault rows excluded
    outside the vault lane)."""
    from api.memory.backfill import search_archive
    from api.observability import lanes
    return await search_archive(q, limit=min(limit, 50), vault_visible=lanes.get_lane() == "vault")


@router.get("/loops")
async def get_open_loops() -> list[dict[str, Any]]:
    from api.memory.commitments import open_loops
    return await open_loops()


@router.post("/loops/{commitment_id}/resolve")
async def resolve_loop(commitment_id: str, status: str = "done") -> dict[str, Any]:
    from api.memory.commitments import resolve
    try:
        ok = await resolve(commitment_id, status)
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(400, str(e)) from e
    return {"ok": ok}


@router.get("/dossiers/{contact}")
async def get_dossier(contact: str) -> dict[str, Any]:
    from api.memory.dossiers import dossier_for
    md = await dossier_for(contact)
    from fastapi import HTTPException
    if md is None:
        raise HTTPException(404, "no dossier for that contact yet")
    return {"contact": contact, "dossier": md}


@router.get("/decisions")
async def list_decisions(limit: int = 50) -> list[dict[str, Any]]:
    rows = await db.fetch(
        "select id::text, title, body, decided_at, tags from decisions "
        "order by decided_at desc limit $1",
        limit,
    )
    return [_serialize(r) for r in rows]


@router.post("/decisions")
async def add_decision(payload: DecisionIn) -> dict[str, Any]:
    row = await db.fetchrow(
        """insert into decisions (title, body, tags) values ($1, $2, $3)
           returning id::text, title, body, decided_at, tags""",
        payload.title,
        payload.body,
        payload.tags,
    )
    if not row:
        raise HTTPException(500, "insert failed")
    return _serialize(row)


@router.get("/search")
async def search(q: str, limit: int = 10) -> list[dict[str, Any]]:
    return await retrieve_relevant(q, limit=limit)


# ----- memory tree -----


@router.get("/tree/brief")
async def tree_brief(period: str = "today") -> dict[str, Any]:
    node = await tree_engine.get_brief(period=period)
    if not node:
        return {"present": False, "period": period}
    return {"present": True, "period": period, **node.__dict__}


@router.get("/tree/recent")
async def tree_recent(depth: int = 3, limit: int = 14) -> list[dict[str, Any]]:
    nodes = await tree_engine.walk_recent(depth=depth, limit=limit)
    return [n.__dict__ for n in nodes]


@router.get("/tree/search")
async def tree_search(q: str, limit: int = 8) -> list[dict[str, Any]]:
    nodes = await tree_engine.search(q, limit=limit)
    return [n.__dict__ for n in nodes]


@router.post("/tree/summarize")
async def tree_summarize() -> dict[str, Any]:
    """trigger a manual roll-up. cron will call this every ~15 min."""
    return await tree_engine.summarize_pending()


@router.post("/autofetch")
async def memory_autofetch() -> dict[str, Any]:
    """trigger every integration fetcher once. background loop also does this every 15 min."""
    counts = await autofetch.run_once()
    counts["total"] = sum(counts.values())
    return counts


@router.post("/imessage/poll")
async def memory_imessage_poll() -> dict[str, Any]:
    """trigger the imessage listener once. handy after granting Full Disk Access."""
    from api.listeners import imessage as listener
    return await listener.run_once()


@router.post("/telegram/poll")
async def memory_telegram_poll() -> dict[str, Any]:
    """trigger the telegram listener once. handy right after setting the bot token."""
    from api.listeners import telegram as listener
    return await listener.run_once()


@router.post("/email/poll")
async def memory_email_poll() -> dict[str, Any]:
    """trigger the email listener once. scans newer_than:1d for mentions of ro."""
    from api.listeners import email as listener
    return await listener.run_once()


@router.get("/browser/profiles")
async def list_browser_profiles() -> dict[str, Any]:
    """which hosts have a persistent browser profile saved."""
    from api.integrations import browser
    return {"profiles": browser.list_profiles(), "root": str(browser.PROFILE_ROOT)}


# ----- entities -----


@router.get("/entities")
async def list_entities(q: str = "", limit: int = 20) -> list[dict[str, Any]]:
    """fuzzy search the entity graph. empty q returns the most-seen recently."""
    if q.strip():
        ents = await entities_mod.find_entity(q, limit=limit)
        return [e.__dict__ for e in ents]
    rows = await db.fetch(
        """select id::text, kind, name, coalesce(summary,'') as summary,
                  seen_count, last_seen_at
           from entities order by last_seen_at desc nulls last limit $1""",
        limit,
    )
    return [{**dict(r), "last_seen_at": r["last_seen_at"].isoformat() if r["last_seen_at"] else ""} for r in rows]


@router.get("/entities/profile")
async def entity_profile_route(name: str) -> dict[str, Any]:
    prof = await entities_mod.entity_profile(name)
    if not prof:
        return {"found": False}
    return {"found": True, **prof}


@router.post("/entities/extract")
async def trigger_extract(limit: int = 80) -> dict[str, Any]:
    """manual trigger. background loop runs every 30 min."""
    return await entities_mod.run_extraction(limit=limit)


def _serialize(row: Any) -> dict[str, Any]:
    out = dict(row)
    for k, v in list(out.items()):
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif isinstance(v, (dict, list)) and not isinstance(v, str):
            try:
                json.dumps(v)
            except TypeError:
                out[k] = str(v)
    return out
