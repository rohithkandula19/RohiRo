"""memory routes. profile crud, contacts, decisions, conversation search."""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.memory.db import db
from api.memory.retrieval import retrieve_relevant

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
