"""files sub-agent — google drive wired.

intents:
- list_recent  "what files have i opened lately"
- search       "find files about photon" / "search drive for offer"
- read         "open my resume" / "show me the docx i made yesterday"
- summarize    "summarize the photon brief"
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from typing import Any

from api.agents.base import Agent, AgentResult
from api.config import settings
from api.integrations import gdrive
from api.observability.logging import log

INTENT_PROMPT = """classify a request about files into one intent and extract a search term.

intents:
- "list_recent": user wants recent files (latest, what have i opened, list my files)
- "search": user wants to find files by name or content (find, search, look for)
- "read": user wants the contents of a specific file
- "summarize": user wants a one-paragraph summary of a file
- "other": none of the above

params:
- "query": the search keyword(s), else ""
- "filename": a specific filename if mentioned, else ""

reply with json only:
{"intent": "...", "query": "...", "filename": "..."}"""


class FilesAgent(Agent):
    async def run(self, *, session_id: str, user_text: str, context: dict[str, Any]) -> AgentResult:
        if not gdrive.configured():
            return AgentResult(
                text=(
                    "i can't reach drive yet — your google account isn't connected.\n\n"
                    "one-time setup:\n"
                    "  1. https://console.cloud.google.com/ → enable drive api\n"
                    "  2. save oauth json to ~/.config/ro/google_client.json\n"
                    "  3. run `uv run python scripts/setup_google_oauth.py`\n"
                    "(if you already did this for gmail/calendar, run the script again to add drive scope.)"
                ),
                error="drive_not_configured",
            )

        intent = await self._classify(user_text)
        kind = intent.get("intent", "other")

        if kind == "list_recent":
            return await self._list_recent()
        if kind == "search":
            return await self._search(intent, user_text)
        if kind == "read":
            return await self._read(intent, user_text)
        if kind == "summarize":
            return await self._summarize(intent, user_text)

        # fall back to a search if there's any signal in the query, else list
        if (intent.get("query") or intent.get("filename")):
            return await self._search(intent, user_text)
        return await self._list_recent()

    # ----- intents -----

    async def _list_recent(self) -> AgentResult:
        try:
            files = await gdrive.list_recent_files(limit=15)
        except Exception as e:
            return AgentResult(text=f"couldn't list drive files. {e}", error=str(e))
        if not files:
            return AgentResult(text="no recent drive files.")

        lines = [f"{len(files)} recent files:"]
        for f in files[:15]:
            ext = _label_mime(f.mime_type)
            lines.append(f"• {f.name}  ({ext})")

        return AgentResult(
            text="\n".join(lines),
            tool_calls=[{
                "tool": "drive.list",
                "args": {},
                "result": [asdict(f) for f in files],
            }],
        )

    async def _search(self, intent: dict[str, Any], user_text: str) -> AgentResult:
        q = (intent.get("query") or intent.get("filename") or "").strip()
        if not q:
            # try to pull a noun out of the user text
            q = _fallback_query(user_text)
        if not q:
            return AgentResult(text="what should i search drive for?")
        try:
            files = await gdrive.search_files(q, limit=12)
        except Exception as e:
            return AgentResult(text=f"drive search failed. {e}", error=str(e))
        if not files:
            return AgentResult(text=f"no drive files matching `{q}`.")

        lines = [f"{len(files)} matching `{q}`:"]
        for f in files:
            lines.append(f"• {f.name}  ({_label_mime(f.mime_type)})")
        return AgentResult(
            text="\n".join(lines),
            tool_calls=[{
                "tool": "drive.search",
                "args": {"query": q},
                "result": [asdict(f) for f in files],
            }],
        )

    async def _read(self, intent: dict[str, Any], user_text: str) -> AgentResult:
        target = (intent.get("filename") or intent.get("query") or "").strip()
        if not target:
            return AgentResult(text="which file should i open?")
        try:
            files = await gdrive.search_files(target, limit=3)
        except Exception as e:
            return AgentResult(text=f"drive search failed. {e}", error=str(e))
        if not files:
            return AgentResult(text=f"no drive file matching `{target}`.")
        head = files[0]
        try:
            content = await gdrive.get_file_text(head.file_id, max_chars=6000)
        except Exception as e:
            return AgentResult(text=f"couldn't read `{head.name}`. {e}", error=str(e))

        return AgentResult(
            text=f"`{head.name}` — first 6000 chars:",
            tool_calls=[{
                "tool": "drive.read",
                "args": {"file": head.name},
                "result": {
                    "file_id": head.file_id, "name": head.name,
                    "mime_type": head.mime_type, "web_view": head.web_view,
                    "content": content,
                },
            }],
        )

    async def _summarize(self, intent: dict[str, Any], user_text: str) -> AgentResult:
        target = (intent.get("filename") or intent.get("query") or "").strip()
        if not target:
            return AgentResult(text="which file should i summarize?")
        try:
            files = await gdrive.search_files(target, limit=3)
        except Exception as e:
            return AgentResult(text=f"drive search failed. {e}", error=str(e))
        if not files:
            return AgentResult(text=f"no drive file matching `{target}`.")
        head = files[0]
        try:
            content = await gdrive.get_file_text(head.file_id, max_chars=12000)
        except Exception as e:
            return AgentResult(text=f"couldn't read `{head.name}`. {e}", error=str(e))

        if not content.strip() or content.startswith("[binary"):
            return AgentResult(text=f"`{head.name}` looks binary — i can't summarize it.")

        sys = "summarize this document in 4-6 sentences plus 2-4 bullets of the most important specifics."
        prompt = f"file: {head.name}\nmimeType: {head.mime_type}\n\nbody:\n\n{content}"
        try:
            resp = await self._ask(
                system=sys,
                messages=[{"role": "user", "content": prompt}],
                model=settings.model_default,
                max_tokens=600,
                temperature=0.4,
            )
        except Exception as e:
            resp = f"(couldn't draft summary: {e})"

        return AgentResult(
            text=f"**{head.name}**\n\n{resp}",
            tool_calls=[{
                "tool": "drive.summary",
                "args": {"file": head.name},
                "result": {
                    "file_id": head.file_id, "name": head.name,
                    "mime_type": head.mime_type, "web_view": head.web_view,
                    "summary": resp,
                },
            }],
        )

    # ----- planner -----

    async def _classify(self, text: str) -> dict[str, Any]:
        try:
            raw = await self._ask(
                system=INTENT_PROMPT,
                messages=[{"role": "user", "content": text}],
                model=settings.model_cheap,
                max_tokens=140,
                temperature=0.0,
            )
            if raw.startswith("```"):
                raw = raw.strip("`")
                if raw.lower().startswith("json"):
                    raw = raw[4:]
            return json.loads(raw)
        except Exception:
            return {"intent": "other", "query": "", "filename": ""}


def _label_mime(mime: str) -> str:
    if mime == "application/vnd.google-apps.document": return "doc"
    if mime == "application/vnd.google-apps.spreadsheet": return "sheet"
    if mime == "application/vnd.google-apps.presentation": return "slides"
    if mime == "application/vnd.google-apps.folder": return "folder"
    if "/" in mime: return mime.split("/")[-1][:8]
    return mime[:8]


def _fallback_query(t: str) -> str:
    """pull the most likely keyword out of a free-text request."""
    stripped = re.sub(r"[^a-zA-Z0-9 ]", " ", t.lower())
    stop = {"find", "show", "search", "drive", "file", "files", "my", "the", "a", "for",
            "open", "read", "give", "me", "summarize", "about", "with", "from", "and"}
    tokens = [tok for tok in stripped.split() if len(tok) > 2 and tok not in stop]
    return tokens[0] if tokens else ""


files_agent = FilesAgent(name="files", system_prompt="")
