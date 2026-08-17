"""execute approved actions.

routes by `tool` field on the action_log row. each tool knows how to do its
own thing. errors are caught and stored on the row so the ui can surface them.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from datetime import datetime
from api.integrations import browser as browser_int, gcal, gmail, imessage as imsg, linear as linear_int, notion as notion_int, slack as slack_int, system as system_int, telegram as tg_int, vision as vision_int, whatsapp as wa_int
from api.scheduler import create as schedule_create
from api.memory.db import db
from api.memory.tree import write_event as tree_write
from api.observability.logging import log
from api.supervisor import approval


async def execute(action_id: uuid.UUID) -> dict[str, Any]:
    """execute an approved or edited action exactly once.

    the claim is a compare-and-swap to status 'executing': concurrent callers
    race for the claim and exactly one wins. a crash after the provider send
    leaves the row in 'executing', which is never re-claimable, so a retry can
    never double-send. the row surfaces in the ui as stuck-executing with the
    provider result missing, which is honest.
    """
    claimed = await approval.claim_for_execute(action_id)
    if claimed is None:
        current = await db.fetchrow("select status from action_log where id = $1", action_id)
        status = current["status"] if current else "missing"
        return {"ok": False, "error": f"action is {status}, not executable", "status": status}

    payload = claimed["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    edit_note = claimed["edit_note"]
    tool = claimed["tool"]

    try:
        result = await _dispatch(tool, payload, edit_note)
        await approval.mark_executed(action_id, result=result)
        # auto-capture: write the act into the tree
        try:
            await tree_write(
                source=_source_for_tool(tool),
                kind=tool,
                summary=_describe(tool, payload, result),
                payload={"result": result, "action_id": str(action_id)},
            )
        except Exception:
            log.warning("tree write failed (execute)", tool=tool)
        return {"ok": True, "tool": tool, "result": result}
    except Exception as e:  # noqa: BLE001
        log.exception("execute failed", action_id=str(action_id), tool=tool)
        await approval.mark_executed(action_id, error=str(e))
        return {"ok": False, "tool": tool, "error": str(e)}


def _source_for_tool(tool: str) -> str:
    if tool.startswith("gmail."):
        return "gmail"
    if tool.startswith("calendar."):
        return "calendar"
    if tool.startswith("slack."):
        return "slack"
    if tool.startswith("imessage."):
        return "imessage"
    if tool.startswith("telegram."):
        return "telegram"
    if tool.startswith("whatsapp."):
        return "whatsapp"
    if tool in ("shell.run", "file.write", "web.fetch", "browser.render", "browser.step", "vision.ask"):
        return "actions"
    if tool.startswith("notion."):
        return "notion"
    if tool.startswith("linear."):
        return "linear"
    return "action"


def _describe(tool: str, payload: dict, result: dict) -> str:
    if tool == "gmail.send_draft" or tool == "gmail.send":
        return f"sent email to {payload.get('to','?')}: {payload.get('subject','')[:80]}"
    if tool == "calendar.create_event":
        return f"booked '{payload.get('title','?')}' at {payload.get('start','')}"
    if tool == "slack.post_message":
        target = payload.get("channel_name") or payload.get("channel_id")
        return f"slack → {target}: {(payload.get('body') or '')[:100]}"
    if tool == "imessage.send":
        return f"text → {payload.get('handle','?')}: {(payload.get('body') or '')[:100]}"
    if tool == "telegram.send":
        who = payload.get('to_name') or payload.get('chat_id','?')
        return f"telegram → {who}: {(payload.get('body') or '')[:100]}"
    if tool == "whatsapp.send":
        who = payload.get('to_name') or payload.get('to','?')
        return f"whatsapp → {who}: {(payload.get('body') or '')[:100]}"
    if tool == "shell.run":
        ec = result.get("exit_code", "?")
        return f"shell `{payload.get('command','')[:90]}` (exit {ec})"
    if tool == "file.write":
        return f"wrote {result.get('bytes',0)}B to {result.get('path','?')}"
    if tool == "web.fetch":
        return f"{payload.get('method','GET')} {payload.get('url','?')} → {result.get('status','?')}"
    if tool == "browser.render":
        return f"rendered {payload.get('url','?')} → {result.get('status','?')} ({result.get('title','')[:60]})"
    if tool == "vision.ask":
        return f"vision: {payload.get('source','?')} → '{(result.get('text') or '')[:80]}'"
    if tool == "browser.step":
        s = payload.get("step", "?")
        if s == "goto":   return f"browser goto {payload.get('url','?')}"
        if s == "click":  return f"browser click '{payload.get('text','?')[:60]}'"
        if s == "fill":   return f"browser fill '{payload.get('label','?')[:40]}' = '{(payload.get('value') or '')[:40]}'"
        if s == "scroll": return f"browser scroll {payload.get('pixels','?')}px"
        if s == "close":  return "browser session closed"
        return f"browser {s}"
    if tool == "notion.create_page":
        return f"created notion page '{payload.get('title','?')}' under '{payload.get('parent_title','?')}'"
    if tool == "notion.append_blocks":
        return f"appended {result.get('appended','?')} blocks to '{payload.get('page_title','?')}'"
    if tool == "linear.create_issue":
        return f"linear: created {result.get('identifier','?')} '{result.get('title','')[:60]}'"
    if tool == "linear.add_comment":
        return f"linear: commented on {result.get('issue','?')}"
    return f"{tool} executed"


async def _dispatch(tool: str, payload: dict[str, Any], edit_note: Any) -> dict[str, Any]:
    # if user edited, prefer the edited body
    body = (edit_note or payload.get("body") or "").strip()

    if tool == "gmail.send_draft":
        # if user edited, we can't reuse the original draft id (it has the old body)
        if edit_note and edit_note.strip() and edit_note.strip() != (payload.get("body") or "").strip():
            sent = await gmail.send_message(
                to=payload["to"],
                subject=payload["subject"],
                body=edit_note.strip(),
                thread_id=payload.get("thread_id"),
            )
        else:
            sent = await gmail.send_draft(payload["draft_id"])
        return {"message_id": sent.message_id, "thread_id": sent.thread_id}

    if tool == "gmail.send":
        sent = await gmail.send_message(
            to=payload["to"],
            subject=payload["subject"],
            body=body,
            thread_id=payload.get("thread_id"),
        )
        return {"message_id": sent.message_id, "thread_id": sent.thread_id}

    if tool == "imessage.send":
        text = (edit_note.strip() if edit_note and edit_note.strip() else payload["body"])
        ok = await imsg.send_message(payload["handle"], text)
        if not ok:
            raise RuntimeError("iMessage send failed (osascript). check Messages.app is open and the handle is iMessage-registered.")
        return {"to": payload["handle"], "delivered": True}

    if tool == "telegram.send":
        text = (edit_note.strip() if edit_note and edit_note.strip() else payload["body"])
        res = await tg_int.send_message(int(payload["chat_id"]), text)
        return {"chat_id": payload["chat_id"], "message_id": res.get("message_id"), "to_name": payload.get("to_name", "")}

    if tool == "whatsapp.send":
        text = (edit_note.strip() if edit_note and edit_note.strip() else payload["body"])
        res = await wa_int.send_message(payload["to"], text)
        return {"to": payload["to"], "to_name": payload.get("to_name", ""),
                "sid": res.get("sid"), "status": res.get("status")}

    if tool == "slack.post_message":
        # use edit_note if user edited
        text = (edit_note.strip() if edit_note and edit_note.strip() else payload["body"])
        res = await slack_int.post_message(payload["channel_id"], text)
        return res

    if tool == "calendar.create_event":
        start = datetime.fromisoformat(payload["start"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(payload["end"].replace("Z", "+00:00"))
        ev = await gcal.create_event(
            title=payload["title"],
            start=start,
            end=end,
            description=payload.get("description", ""),
            location=payload.get("location", ""),
            attendees=payload.get("attendees", []) or None,
            add_meet_link=payload.get("add_meet_link", False),
        )
        return {
            "event_id": ev.event_id,
            "title": ev.title,
            "start": ev.start,
            "end": ev.end,
            "hangout_link": ev.hangout_link,
        }

    if tool == "notion.create_page":
        body = edit_note.strip() if edit_note and edit_note.strip() else payload.get("body", "")
        res = await notion_int.create_page(
            parent_id=payload["parent_id"],
            title=payload["title"],
            body=body,
        )
        return res

    if tool == "notion.append_blocks":
        body = edit_note.strip() if edit_note and edit_note.strip() else payload.get("body", "")
        res = await notion_int.append_blocks(page_id=payload["page_id"], body=body)
        return res

    if tool == "linear.create_issue":
        # honour edited title/description via edit_note? for linear we keep payload simple
        res = await linear_int.create_issue(
            team_key=payload["team_key"],
            title=payload["title"],
            description=payload.get("description", ""),
            priority=int(payload.get("priority", 0)),
        )
        return res

    if tool == "linear.add_comment":
        body = edit_note.strip() if edit_note and edit_note.strip() else payload["body"]
        res = await linear_int.add_comment(payload["identifier"], body)
        return res

    if tool == "shell.run":
        res = await system_int.run_shell(payload["command"])
        return {
            "exit_code": res.exit_code,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "duration_ms": res.duration_ms,
            "truncated": res.truncated,
        }

    if tool == "file.write":
        # honour the edit_note if user changed the content during approval
        content = edit_note if edit_note else payload["content"]
        res = await system_int.write_file(
            path=payload["path"],
            content=content,
            append=bool(payload.get("append", False)),
        )
        return {"path": res.path, "bytes": res.bytes_written}

    if tool == "web.fetch":
        res = await system_int.web_fetch(
            payload["url"],
            method=payload.get("method", "GET"),
            headers=payload.get("headers") or None,
            body=payload.get("body"),
        )
        return {
            "status": res.status,
            "url": res.url,
            "headers": res.headers,
            "body": res.body,
            "truncated": res.truncated,
        }

    if tool == "schedule.create":
        sid = await schedule_create(
            kind=payload["kind"],
            spec=payload["spec"],
            text=payload["text"],
            title=payload.get("title", ""),
            tz=payload.get("timezone", "UTC"),
        )
        return {"schedule_id": sid, "next_at": payload.get("next_at"),
                "title": payload.get("title", ""), "text": payload.get("text", "")}

    if tool == "browser.render":
        res = await browser_int.render(payload["url"])
        return {
            "url": res.url,
            "final_url": res.final_url,
            "title": res.title,
            "text": res.text,
            "screenshot_b64": res.screenshot_b64,
            "status": res.status,
            "truncated": res.truncated,
        }

    if tool == "vision.ask":
        prompt = payload.get("prompt") or "describe this image."
        if payload.get("kind") == "url":
            text = await vision_int.describe_url(payload["source"], prompt=prompt)
        else:
            text = await vision_int.describe_image_path(payload["source"], prompt=prompt)
        return {"source": payload.get("source"), "prompt": prompt, "text": text}

    if tool == "browser.step":
        key = payload.get("session_key") or "default"
        step = payload["step"]
        if step == "close":
            ok = await browser_int.close_session(key)
            return {"action": "close", "closed": ok}
        session = await browser_int.get_session(key)
        if step == "goto":
            r = await session.goto(payload["url"])
        elif step == "click":
            r = await session.click(payload["text"])
        elif step == "fill":
            r = await session.fill(payload["label"], payload["value"])
        elif step == "scroll":
            r = await session.scroll(int(payload.get("pixels", 600)))
        else:
            raise ValueError(f"unknown browser step: {step}")
        return {
            "action": r.action,
            "final_url": r.final_url,
            "title": r.title,
            "text": r.text,
            "screenshot_b64": r.screenshot_b64,
            "elements": r.elements,
            "truncated": r.truncated,
            "note": r.note,
        }

    raise ValueError(f"unknown tool: {tool}")
