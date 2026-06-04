"""notion client.

uses an integration token from keychain (`notion_token`). create one at
https://www.notion.so/my-integrations and share each page/database with the
integration so it's visible.

verbs:
- configured()
- search(query, kinds='page,database', limit=15)    -> list[Hit]
- get_page(page_id)                                  -> Page
- get_page_content(page_id, max_blocks=200)          -> str  (markdown-ish)
- create_page(parent_id, title, body)                -> dict
- append_blocks(page_id, body)                       -> dict
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from api.config import secrets
from api.observability.logging import log

API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


@dataclass
class Hit:
    object_kind: str   # "page" | "database"
    page_id: str
    title: str
    url: str
    last_edited_at: str = ""
    parent_kind: str = ""
    icon: str = ""


@dataclass
class Page:
    page_id: str
    title: str
    url: str
    icon: str = ""
    properties: dict[str, Any] = field(default_factory=dict)
    last_edited_at: str = ""


def configured() -> bool:
    return bool(secrets.get("notion_token"))


def _headers() -> dict[str, str]:
    token = secrets.get("notion_token")
    if not token:
        raise RuntimeError(
            "notion not configured. create an integration at https://www.notion.so/my-integrations, "
            "share your pages with it, then `keyring set ro notion_token`."
        )
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _title_of(obj: dict[str, Any]) -> str:
    # pages: title is in properties.<title-key>.title[]
    # databases: title is at the object level
    if obj.get("object") == "database":
        parts = obj.get("title") or []
        return "".join(p.get("plain_text", "") for p in parts) or "(untitled)"
    props = obj.get("properties") or {}
    for v in props.values():
        if v.get("type") == "title":
            parts = v.get("title") or []
            return "".join(p.get("plain_text", "") for p in parts) or "(untitled)"
    return "(untitled)"


def _icon_of(obj: dict[str, Any]) -> str:
    icon = obj.get("icon")
    if not icon:
        return ""
    if icon.get("type") == "emoji":
        return icon.get("emoji", "")
    return ""


# ----- search / get -----


async def search(query: str = "", kinds: str = "page,database", limit: int = 15) -> list[Hit]:
    body: dict[str, Any] = {"page_size": min(100, max(1, limit))}
    if query.strip():
        body["query"] = query.strip()
    filter_kind: Optional[str] = None
    parts = [k.strip() for k in kinds.split(",") if k.strip()]
    if len(parts) == 1 and parts[0] in ("page", "database"):
        filter_kind = parts[0]
        body["filter"] = {"value": filter_kind, "property": "object"}

    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.post(f"{API}/search", headers=_headers(), json=body)
        if r.status_code != 200:
            log.warning("notion search failed", status=r.status_code, body=r.text[:300])
            return []
        items = r.json().get("results", [])
        out: list[Hit] = []
        for it in items[:limit]:
            kind = it.get("object", "page")
            out.append(Hit(
                object_kind=kind,
                page_id=it.get("id", ""),
                title=_title_of(it),
                url=it.get("url", ""),
                last_edited_at=it.get("last_edited_time", ""),
                parent_kind=(it.get("parent") or {}).get("type", ""),
                icon=_icon_of(it),
            ))
        return out


async def get_page(page_id: str) -> Page:
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.get(f"{API}/pages/{page_id}", headers=_headers())
        r.raise_for_status()
        obj = r.json()
        return Page(
            page_id=obj["id"],
            title=_title_of(obj),
            url=obj.get("url", ""),
            icon=_icon_of(obj),
            properties=obj.get("properties") or {},
            last_edited_at=obj.get("last_edited_time", ""),
        )


# ----- content extraction (blocks -> markdown-ish text) -----


async def get_page_content(page_id: str, max_blocks: int = 200, max_chars: int = 16000) -> str:
    async with httpx.AsyncClient(timeout=20.0) as c:
        out: list[str] = []
        cursor: Optional[str] = None
        fetched = 0
        while fetched < max_blocks:
            params: dict[str, Any] = {"page_size": min(100, max_blocks - fetched)}
            if cursor:
                params["start_cursor"] = cursor
            r = await c.get(f"{API}/blocks/{page_id}/children", headers=_headers(), params=params)
            if r.status_code != 200:
                log.warning("notion blocks failed", status=r.status_code)
                break
            data = r.json()
            for b in data.get("results", []):
                out.append(_block_to_text(b))
            fetched += len(data.get("results", []))
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
        text = "\n".join(t for t in out if t is not None)
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n\n…[truncated at {max_chars} chars]"
        return text


def _rt(rt: list[dict[str, Any]] | None) -> str:
    return "".join((r or {}).get("plain_text", "") for r in (rt or []))


def _block_to_text(b: dict[str, Any]) -> str:
    t = b.get("type", "")
    body = b.get(t) or {}
    text = _rt(body.get("rich_text"))
    if t in {"paragraph", "quote"}:
        return text or ""
    if t == "heading_1":
        return f"# {text}"
    if t == "heading_2":
        return f"## {text}"
    if t == "heading_3":
        return f"### {text}"
    if t == "bulleted_list_item":
        return f"- {text}"
    if t == "numbered_list_item":
        return f"1. {text}"
    if t == "to_do":
        check = "x" if body.get("checked") else " "
        return f"- [{check}] {text}"
    if t == "code":
        lang = body.get("language", "")
        return f"```{lang}\n{text}\n```"
    if t == "callout":
        return f"> {text}"
    if t == "divider":
        return "---"
    if t == "child_page":
        return f"📄 {body.get('title','(child page)')}"
    return text or ""


# ----- write (approval-gated; called from execute) -----


async def create_page(*, parent_id: str, title: str, body: str) -> dict[str, Any]:
    """create a page inside `parent_id` (page or database)."""
    blocks = _markdown_to_blocks(body)
    payload: dict[str, Any] = {
        "parent": {"type": "page_id", "page_id": parent_id},
        "properties": {"title": {"title": [{"type": "text", "text": {"content": title or "(untitled)"}}]}},
        "children": blocks,
    }
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.post(f"{API}/pages", headers=_headers(), json=payload)
        if r.status_code != 200:
            raise RuntimeError(f"notion create failed: {r.status_code} {r.text[:200]}")
        obj = r.json()
        return {"page_id": obj.get("id"), "url": obj.get("url")}


async def append_blocks(*, page_id: str, body: str) -> dict[str, Any]:
    blocks = _markdown_to_blocks(body)
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.patch(
            f"{API}/blocks/{page_id}/children",
            headers=_headers(),
            json={"children": blocks},
        )
        if r.status_code != 200:
            raise RuntimeError(f"notion append failed: {r.status_code} {r.text[:200]}")
        return {"appended": len(blocks), "page_id": page_id}


def _markdown_to_blocks(body: str) -> list[dict[str, Any]]:
    """tiny markdown -> notion blocks. handles headings, bullets, code fences, paragraphs."""
    out: list[dict[str, Any]] = []
    lines = body.splitlines()
    in_code = False
    code_lines: list[str] = []
    code_lang = ""
    for line in lines:
        if line.startswith("```"):
            if in_code:
                out.append({"object": "block", "type": "code",
                            "code": {"language": code_lang or "plain text",
                                     "rich_text": [{"type": "text", "text": {"content": "\n".join(code_lines)}}]}})
                code_lines = []
                code_lang = ""
                in_code = False
            else:
                code_lang = line[3:].strip() or ""
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        if line.startswith("### "):
            out.append(_p("heading_3", line[4:]))
        elif line.startswith("## "):
            out.append(_p("heading_2", line[3:]))
        elif line.startswith("# "):
            out.append(_p("heading_1", line[2:]))
        elif line.startswith("- "):
            out.append(_p("bulleted_list_item", line[2:]))
        elif line.startswith("> "):
            out.append(_p("quote", line[2:]))
        elif line.strip() == "":
            continue
        else:
            out.append(_p("paragraph", line))
    if in_code and code_lines:
        out.append({"object": "block", "type": "code",
                    "code": {"language": code_lang or "plain text",
                             "rich_text": [{"type": "text", "text": {"content": "\n".join(code_lines)}}]}})
    return out


def _p(kind: str, text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": kind,
        kind: {"rich_text": [{"type": "text", "text": {"content": text}}]},
    }
