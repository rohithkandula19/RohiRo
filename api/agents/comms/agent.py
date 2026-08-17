"""comms sub-agent — gmail-wired.

three intents the supervisor routes here:

1. read  ("show me recent emails", "what did sarah say")
   → call gmail.search_threads, return a structured list, no approval needed.
2. draft ("reply to sarah saying tuesday works", "draft an email to alice")
   → pull thread context if a reply, draft with claude, open approval row,
     stash thread_id + to/subject/body on the action so execute() can send.
3. send  → handled by the supervisor's approval/execute path, not here.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict
from typing import Any, Optional

from api.agents.base import Agent, AgentResult
from api.config import settings
from api.eval.voice_learner import load_voice
from api.integrations import gmail, imessage as imsg, slack as slack_int, telegram as tg_int, whatsapp as wa_int
from api.memory.retrieval import get_profile_body
from api.observability.logging import log
from api.supervisor import approval

VOICE = """ro's voice: direct, warm, short sentences. no em dashes. sentence case.
no corporate filler. no "i hope this helps". no "let me know if you need anything".
draft only. never claim it's sent. when ro asks you to reply, draft as if ro is writing.
return only the body of the message, nothing else, no preamble."""


async def _voice_for(channel: str) -> str:
    """base VOICE + learned rules for this channel, if any."""
    extra = await load_voice(channel)
    if not extra or extra.strip().startswith("- (not enough"):
        return VOICE
    return VOICE + "\n\n## learned from ro's edits\n\n" + extra.strip()

INTENT_PROMPT = """classify the user's request into one intent and detect the channel.

intents:
- "read": user wants to see existing messages (show, list, find, what did X say)
- "draft_reply": user wants to reply to an existing thread (reply to, respond to, get back to)
- "draft_new": user wants to send a new message (draft, write to, send a note to, message X, dm X)
- "other": none of the above

channels:
- "gmail" (default for "email", "mail", or unspecified comms)
- "slack" (if user says "slack", "on slack", "channel", "#general")
- "imessage" (if user says "imessage", "text", "message my", "text mom", "send a text")
- "telegram" (if user says "telegram", "tg", "on telegram", or mentions telegram chat_id)
- "whatsapp" (if user says "whatsapp", "wa", "on whatsapp", or mentions a number with country code in whatsapp context)
- "auto" if not clearly stated and not clearly email — pick gmail.

also extract:
- query: a search string if obvious, else ""
- target: a person name, email, channel name, or handle if mentioned, else ""

reply with json only, shape:
{"intent": "...", "channel": "...", "query": "...", "target": "..."}"""


class CommsAgent(Agent):
    async def run(self, *, session_id: str, user_text: str, context: dict[str, Any]) -> AgentResult:
        intent = await self._classify_intent(user_text)
        intent_kind = intent.get("intent", "other")
        channel = intent.get("channel", "gmail")
        if channel == "auto":
            channel = "gmail"

        if channel == "whatsapp":
            if not wa_int.configured():
                return AgentResult(
                    text=(
                        "i can't reach whatsapp yet.\n\n"
                        "one-time setup (free, no business verification):\n"
                        "  1. twilio.com → Develop → Messaging → Try it out → Send a WhatsApp message\n"
                        "  2. join the sandbox from your phone (text 'join <code>' to the sandbox number)\n"
                        "  3. `keyring set ro twilio_account_sid`     (starts with AC...)\n"
                        "  4. `keyring set ro twilio_auth_token`\n"
                        "  5. `keyring set ro whatsapp_from`          (the sandbox number, e.g. +14155238886)\n"
                        "  6. point twilio's inbound webhook at  <ro-url>/webhooks/whatsapp"
                    ),
                    error="whatsapp_not_configured",
                )
            if intent_kind in ("draft_new", "draft_reply"):
                return await self._whatsapp_draft(intent, user_text, session_id, context)
            return await self._whatsapp_draft({}, user_text, session_id, context)

        if channel == "telegram":
            if not tg_int.configured():
                return AgentResult(
                    text=(
                        "i can't reach telegram yet.\n\n"
                        "one-time setup:\n"
                        "  1. talk to @BotFather, get a bot token\n"
                        "  2. `keyring set ro telegram_bot_token`\n"
                        "  3. (optional but recommended) message your bot once,\n"
                        "     then check /api/listeners debug for your chat id,\n"
                        "     then `keyring set ro telegram_owner_id` to lock it down."
                    ),
                    error="telegram_not_configured",
                )
            if intent_kind in ("draft_new", "draft_reply"):
                return await self._telegram_draft(intent, user_text, session_id, context)
            return await self._telegram_draft({}, user_text, session_id, context)

        if channel == "imessage":
            if not imsg.configured():
                return AgentResult(
                    text=(
                        "i can't reach iMessage yet — chat.db isn't readable.\n\n"
                        "grant Full Disk Access to your terminal/python:\n"
                        "  System Settings → Privacy & Security → Full Disk Access → add your terminal.\n"
                        "then restart the ro api."
                    ),
                    error="imessage_not_configured",
                )
            if intent_kind == "read":
                return await self._imessage_read(intent)
            if intent_kind in ("draft_new", "draft_reply"):
                return await self._imessage_draft(intent, user_text, session_id)
            return await self._imessage_read(intent)

        if channel == "slack":
            if not slack_int.configured():
                return AgentResult(
                    text=(
                        "i can't reach slack yet.\n\n"
                        "one-time setup:\n"
                        "  1. create a slack app at https://api.slack.com/apps\n"
                        "  2. install it to your workspace; grab the user oauth token (xoxp-…)\n"
                        "  3. run `keyring set ro slack_token` and paste the token"
                    ),
                    error="slack_not_configured",
                )
            if intent_kind == "read":
                return await self._slack_read(intent)
            if intent_kind in ("draft_new", "draft_reply"):
                return await self._slack_draft(intent, user_text, session_id)
            return await self._slack_draft({}, user_text, session_id)

        # gmail path
        if not gmail.configured():
            return AgentResult(
                text=(
                    "i can't reach your gmail yet — you haven't connected it.\n\n"
                    "one-time setup:\n"
                    "  1. create an oauth client at https://console.cloud.google.com/\n"
                    "  2. save the json to ~/.config/ro/google_client.json\n"
                    "  3. run `uv run python scripts/setup_google_oauth.py`\n\n"
                    "after that i can read, draft, and send for you."
                ),
                error="gmail_not_configured",
            )

        if intent_kind == "read":
            return await self._read(intent, user_text)
        if intent_kind == "draft_reply":
            return await self._draft_reply(intent, user_text, session_id)
        if intent_kind == "draft_new":
            return await self._draft_new(intent, user_text, session_id, context)

        return await self._draft_new({}, user_text, session_id, context)

    # ----- intents -----

    async def _read(self, intent: dict[str, Any], user_text: str) -> AgentResult:
        q = intent.get("query") or _query_from_text(user_text)
        try:
            threads = await gmail.search_threads(q, max_results=8)
        except Exception as e:
            log.exception("gmail search failed")
            return AgentResult(text=f"couldn't read gmail. {e}", error=str(e))

        if not threads:
            return AgentResult(text=f"nothing matching `{q or 'recent'}`.")

        # one-line summary + structured payload for the ui
        lines = [f"{len(threads)} thread{'s' if len(threads) != 1 else ''}:"]
        for t in threads[:8]:
            who = t.from_name or t.from_email
            tag = " ·  unread" if t.unread else ""
            lines.append(f"• {who} — {t.subject[:80]}{tag}")

        return AgentResult(
            text="\n".join(lines),
            tool_calls=[{
                "tool": "gmail.search",
                "args": {"query": q},
                "result": [asdict(t) for t in threads],
            }],
        )

    async def _draft_reply(self, intent: dict[str, Any], user_text: str, session_id: str) -> AgentResult:
        # find a thread by the target/topic. if multiple candidates, pick the most recent.
        target = intent.get("target", "")
        q_parts = []
        if target:
            # cheap heuristic: if target looks like email, search from:; else use it as a free text + from:
            if "@" in target:
                q_parts.append(f"from:{target}")
            else:
                q_parts.append(f"from:{target}")
        q_parts.append("newer_than:30d")
        q = " ".join(q_parts)

        try:
            threads = await gmail.search_threads(q, max_results=3)
        except Exception as e:
            return AgentResult(text=f"couldn't search gmail. {e}", error=str(e))

        if not threads:
            return AgentResult(
                text=f"no recent thread from {target or 'that person'}. want me to draft a new email instead?",
            )

        head = threads[0]
        try:
            full = await gmail.get_thread(head.thread_id)
        except Exception as e:
            return AgentResult(text=f"couldn't load the thread. {e}", error=str(e))

        last = full.messages[-1] if full.messages else None
        if last is None:
            return AgentResult(text="that thread is empty, weird. nothing to reply to.")

        # draft with claude using the actual last message as context
        profile = await get_profile_body()
        sys = await _voice_for("gmail")
        if profile.strip():
            sys += "\n\n## ro's profile\n\n" + profile.strip()
        # relationship register: how you actually talk to this person
        try:
            from api.memory.dossiers import dossier_for
            dossier = await dossier_for(last.from_email or "")
            if dossier:
                sys += "\n\n## about this person (private dossier)\n\n" + dossier
        except Exception:
            pass

        user = (
            f"the previous message in the thread was from {last.from_name} <{last.from_email}>:\n\n"
            f"---\n{last.body[:4000]}\n---\n\n"
            f"ro's instruction: {user_text}\n\n"
            f"draft a reply. return only the reply body."
        )
        try:
            draft_body = await self._ask(
                system=sys,
                messages=[{"role": "user", "content": user}],
                model=settings.model_default,
                max_tokens=600,
                temperature=0.6,
            )
        except Exception as e:
            return AgentResult(text="", error=f"draft failed: {e}")

        if not draft_body.strip():
            return AgentResult(text="(no draft produced)")

        # create a real gmail draft so the user can also see it in gmail web
        subject = full.subject if full.subject.lower().startswith("re:") else f"Re: {full.subject}"
        try:
            draft = await gmail.create_draft(
                to=last.from_email,
                subject=subject,
                body=draft_body,
                reply_to_thread_id=full.thread_id,
                in_reply_to_message_id=last.message_id,
            )
        except Exception as e:
            log.warning("gmail draft create failed, returning text only", error=str(e))
            draft = None

        action_id = await approval.open_approval(
            session_id=uuid.UUID(session_id),
            domain="comms",
            tool="gmail.send_draft",
            description=f"reply to {last.from_name} re: {full.subject[:60]}",
            payload={
                "draft_id": draft.draft_id if draft else None,
                "to": last.from_email,
                "subject": subject,
                "body": draft_body,
                "thread_id": full.thread_id,
                "in_reply_to_message_id": last.message_id,
                "from_name": last.from_name,
            },
            requires_approval=True,
        )

        return AgentResult(
            text=f"drafted a reply to {last.from_name}:\n\n{draft_body}",
            actions_opened=[str(action_id)],
            tool_calls=[{
                "tool": "gmail.draft_reply",
                "args": {"to": last.from_email, "subject": subject, "thread_id": full.thread_id},
                "result": {
                    "draft_id": draft.draft_id if draft else None,
                    "to": last.from_email,
                    "from_name": last.from_name,
                    "subject": subject,
                    "body": draft_body,
                    "thread_id": full.thread_id,
                },
            }],
        )

    async def _draft_new(
        self,
        intent: dict[str, Any],
        user_text: str,
        session_id: str,
        context: dict[str, Any],
    ) -> AgentResult:
        target = intent.get("target", "")
        # if target looks like an email, use it. otherwise we need to ask the user or look up.
        recipient = target if "@" in target else ""

        profile = await get_profile_body()
        retrieved = context.get("retrieved", []) or []
        ctx_lines = "\n".join(f"- {r.get('body','')[:240]}" for r in retrieved)

        sys = await _voice_for("gmail")
        if profile.strip():
            sys += "\n\n## ro's profile\n\n" + profile.strip()
        if ctx_lines:
            sys += "\n\n## relevant context\n\n" + ctx_lines

        user = (
            f"ro wants to send a new email. ro's instruction: {user_text}\n\n"
            f"return only the body. on the first line of your output before the body, "
            f"write 'SUBJECT: <one-line subject>' followed by a blank line."
        )
        try:
            raw = await self._ask(
                system=sys,
                messages=[{"role": "user", "content": user}],
                model=settings.model_default,
                max_tokens=700,
                temperature=0.6,
            )
        except Exception as e:
            return AgentResult(text="", error=f"draft failed: {e}")

        subject, body = _split_subject(raw)

        # create gmail draft (if we know the recipient)
        draft = None
        if recipient:
            try:
                draft = await gmail.create_draft(to=recipient, subject=subject, body=body)
            except Exception as e:
                log.warning("gmail draft create failed", error=str(e))

        action_id = await approval.open_approval(
            session_id=uuid.UUID(session_id),
            domain="comms",
            tool="gmail.send_draft" if draft else "gmail.send",
            description=f"new email{(' to ' + recipient) if recipient else ''} — {subject[:60]}",
            payload={
                "draft_id": draft.draft_id if draft else None,
                "to": recipient,
                "subject": subject,
                "body": body,
            },
            requires_approval=True,
        )

        hint = "" if recipient else "\n\n(i need the recipient email — tell me where to send it.)"
        return AgentResult(
            text=f"subject: {subject}\n\n{body}{hint}",
            actions_opened=[str(action_id)],
            tool_calls=[{
                "tool": "gmail.draft_new",
                "args": {"to": recipient, "subject": subject},
                "result": {
                    "draft_id": draft.draft_id if draft else None,
                    "to": recipient,
                    "subject": subject,
                    "body": body,
                },
            }],
        )

    # ----- helpers -----

    # ----- whatsapp -----

    async def _whatsapp_draft(self, intent: dict[str, Any], user_text: str, session_id: str, context: dict[str, Any]) -> AgentResult:
        # context wins; else try to pull a +E.164 number out of the text
        to_number: Optional[str] = None
        if isinstance(context, dict) and context.get("whatsapp_to"):
            to_number = str(context["whatsapp_to"]).strip()
        if not to_number:
            m = re.search(r"(\+\d{7,15})", user_text)
            if m:
                to_number = m.group(1)
        if not to_number:
            return AgentResult(text="who should i message on whatsapp? give me a phone number with country code (e.g. +14155551234), or reply to a thread.")

        target_name = ""
        if isinstance(context, dict):
            target_name = (context.get("whatsapp_from_name") or "").strip()

        profile = await get_profile_body()
        sys = await _voice_for("whatsapp")
        if profile.strip():
            sys += "\n\n## ro's profile\n\n" + profile.strip()
        sys += "\n\nthis message is for WHATSAPP. keep it short and casual. no signoff."

        prompt = (
            f"ro's instruction: {user_text}\n\n"
            f"recipient: whatsapp {to_number}"
            + (f" ({target_name})" if target_name else "")
            + "\n\nwrite the message body only."
        )
        try:
            body = await self._ask(
                system=sys,
                messages=[{"role": "user", "content": prompt}],
                model=settings.model_default,
                max_tokens=400,
                temperature=0.6,
            )
        except Exception as e:
            return AgentResult(text="", error=f"whatsapp draft failed: {e}")

        if not body.strip():
            return AgentResult(text="(no draft produced)")

        action_id = await approval.open_approval(
            session_id=uuid.UUID(session_id),
            domain="comms",
            tool="whatsapp.send",
            description=f"whatsapp → {target_name or to_number}",
            payload={"to": to_number, "to_name": target_name, "body": body},
            requires_approval=True,
        )
        return AgentResult(
            text=f"drafted a whatsapp message to {target_name or to_number}:\n\n{body}",
            actions_opened=[str(action_id)],
            tool_calls=[{
                "tool": "whatsapp.draft",
                "args": {"to": to_number},
                "result": {"to": to_number, "to_name": target_name, "body": body},
            }],
        )

    # ----- telegram -----

    async def _telegram_draft(self, intent: dict[str, Any], user_text: str, session_id: str, context: dict[str, Any]) -> AgentResult:
        # accept chat_id from the listener's context, or extract from the user text
        chat_id: Optional[int] = None
        ctx_chat_id = context.get("telegram_chat_id") if isinstance(context, dict) else None
        if isinstance(ctx_chat_id, int):
            chat_id = ctx_chat_id
        else:
            m = re.search(r"chat_id\s*=\s*(-?\d+)", user_text)
            if m:
                chat_id = int(m.group(1))
            else:
                # if owner_id is set, default to DMing them
                owner = tg_int.owner_id()
                if owner is not None:
                    chat_id = owner

        if chat_id is None:
            return AgentResult(text="i need a telegram chat_id. either reply to a chat ro is in, or set telegram_owner_id.")

        target_name = context.get("telegram_from") if isinstance(context, dict) else None

        profile = await get_profile_body()
        sys = await _voice_for("telegram")
        if profile.strip():
            sys += "\n\n## ro's profile\n\n" + profile.strip()
        sys += "\n\nthis message is for telegram. keep it short and casual. no signoff."

        prompt = (
            f"ro's instruction: {user_text}\n\n"
            f"recipient: telegram chat_id={chat_id}"
            + (f" ({target_name})" if target_name else "")
            + "\n\nwrite the message body only."
        )
        try:
            body = await self._ask(
                system=sys,
                messages=[{"role": "user", "content": prompt}],
                model=settings.model_default,
                max_tokens=400,
                temperature=0.6,
            )
        except Exception as e:
            return AgentResult(text="", error=f"telegram draft failed: {e}")

        if not body.strip():
            return AgentResult(text="(no draft produced)")

        action_id = await approval.open_approval(
            session_id=uuid.UUID(session_id),
            domain="comms",
            tool="telegram.send",
            description=f"telegram → {target_name or chat_id}",
            payload={"chat_id": chat_id, "to_name": target_name or "", "body": body},
            requires_approval=True,
        )
        return AgentResult(
            text=f"drafted a telegram reply to {target_name or chat_id}:\n\n{body}",
            actions_opened=[str(action_id)],
            tool_calls=[{
                "tool": "telegram.draft",
                "args": {"chat_id": chat_id},
                "result": {"chat_id": chat_id, "to_name": target_name or "", "body": body},
            }],
        )

    # ----- imessage -----

    async def _imessage_read(self, intent: dict[str, Any]) -> AgentResult:
        target = intent.get("target", "").strip()
        if target:
            msgs = await imsg.recent_with(target, limit=15)
            if not msgs:
                return AgentResult(text=f"no recent iMessage thread matching '{target}'.")
            who = target
            lines = [f"recent iMessages with {who}:"]
            for m in reversed(msgs[:10]):
                speaker = "you" if m.from_me else (m.from_handle or who)
                lines.append(f"• {speaker}: {m.text[:160]}")
            return AgentResult(
                text="\n".join(lines),
                tool_calls=[{
                    "tool": "imessage.history",
                    "args": {"with": who},
                    "result": {
                        "with": who,
                        "messages": [
                            {"from": "you" if m.from_me else (m.from_handle or who),
                             "text": m.text,
                             "at": m.sent_at}
                            for m in reversed(msgs[:10])
                        ],
                    },
                }],
            )

        threads = await imsg.list_recent_threads(limit=10)
        if not threads:
            return AgentResult(text="no recent iMessage threads.")
        lines = [f"{len(threads)} recent iMessage threads:"]
        for t in threads:
            prefix = "you" if t.last_from_me else (t.display_name or "?")
            lines.append(f"• {t.display_name} — {prefix}: {t.last_text[:120]}")
        return AgentResult(
            text="\n".join(lines),
            tool_calls=[{
                "tool": "imessage.threads",
                "args": {},
                "result": [
                    {"name": t.display_name, "last": t.last_text, "from_me": t.last_from_me, "at": t.last_at}
                    for t in threads
                ],
            }],
        )

    async def _imessage_draft(self, intent: dict[str, Any], user_text: str, session_id: str) -> AgentResult:
        target = intent.get("target", "").strip()
        if not target:
            return AgentResult(text="who do i text? give me a name, phone, or email.")

        # resolve handle: if target is a phone/email, use directly; else look up a recent thread by name
        handle = target if ("@" in target or any(ch.isdigit() for ch in target)) else ""
        if not handle:
            recent = await imsg.recent_with(target, limit=1)
            if recent and recent[0].from_handle:
                handle = recent[0].from_handle
            else:
                # try threads
                threads = await imsg.list_recent_threads(limit=50)
                t = next((t for t in threads if target.lower() in (t.display_name or "").lower()), None)
                if t and t.handles:
                    handle = t.handles[0]
        if not handle:
            return AgentResult(text=f"can't resolve '{target}' to an iMessage handle. give me a phone or email.")

        profile = await get_profile_body()
        sys = await _voice_for("imessage")
        if profile.strip():
            sys += "\n\n## ro's profile\n\n" + profile.strip()
        sys += "\n\nthis message is for iMessage. keep it casual and short. no signoff."

        prompt = f"ro's instruction: {user_text}\n\nrecipient: {target}\n\nwrite the message body only."
        try:
            body = await self._ask(
                system=sys,
                messages=[{"role": "user", "content": prompt}],
                model=settings.model_default,
                max_tokens=300,
                temperature=0.6,
            )
        except Exception as e:
            return AgentResult(text="", error=f"imessage draft failed: {e}")

        action_id = await approval.open_approval(
            session_id=uuid.UUID(session_id),
            domain="comms",
            tool="imessage.send",
            description=f"iMessage to {target}",
            payload={"handle": handle, "recipient": target, "body": body},
            requires_approval=True,
        )

        return AgentResult(
            text=f"drafted an iMessage to {target}:\n\n{body}",
            actions_opened=[str(action_id)],
            tool_calls=[{
                "tool": "imessage.draft",
                "args": {"to": target, "handle": handle},
                "result": {"recipient": target, "handle": handle, "body": body},
            }],
        )

    # ----- slack -----

    async def _slack_read(self, intent: dict[str, Any]) -> AgentResult:
        target = intent.get("target", "").strip()
        query = intent.get("query", "").strip()

        # if target points at a person, fetch their dm history
        if target:
            user = await slack_int.find_user_by_name(target)
            if user:
                channel_id = await slack_int.open_dm(user.user_id)
                msgs = await slack_int.fetch_history(channel_id, limit=15)
                lines = [f"recent slack DMs with {user.real_name or user.name}:"]
                for m in reversed(msgs[:10]):
                    who = "you" if not m.user_name else m.user_name
                    lines.append(f"• {who}: {m.text[:140]}")
                return AgentResult(
                    text="\n".join(lines),
                    tool_calls=[{
                        "tool": "slack.history",
                        "args": {"with": user.real_name},
                        "result": {
                            "with": user.real_name,
                            "channel_id": channel_id,
                            "messages": [
                                {"ts": m.ts, "user": m.user_name or "you", "text": m.text}
                                for m in reversed(msgs[:10])
                            ],
                        },
                    }],
                )

        # otherwise, recent dms or a search
        if query:
            try:
                hits = await slack_int.search_messages(query, count=8)
            except Exception as e:
                return AgentResult(text=f"slack search failed (need search:read on token). {e}", error=str(e))
            if not hits:
                return AgentResult(text=f"no slack messages matching `{query}`.")
            lines = [f"{len(hits)} match{'es' if len(hits) != 1 else ''}:"]
            for h in hits:
                lines.append(f"• #{h.channel_name} {h.user_name}: {h.text[:120]}")
            return AgentResult(
                text="\n".join(lines),
                tool_calls=[{
                    "tool": "slack.search",
                    "args": {"query": query},
                    "result": [
                        {"channel": h.channel_name, "user": h.user_name, "text": h.text, "permalink": h.permalink}
                        for h in hits
                    ],
                }],
            )

        # default: recent DMs
        dms = await slack_int.list_recent_dms(limit=8)
        if not dms:
            return AgentResult(text="no recent slack DMs.")
        lines = [f"recent slack DMs:"]
        for d in dms:
            lines.append(f"• {d.name}")
        return AgentResult(
            text="\n".join(lines),
            tool_calls=[{
                "tool": "slack.list_dms",
                "args": {},
                "result": [{"name": d.name, "channel_id": d.channel_id} for d in dms],
            }],
        )

    async def _slack_draft(self, intent: dict[str, Any], user_text: str, session_id: str) -> AgentResult:
        target = intent.get("target", "").strip()
        if not target:
            return AgentResult(text="who should i message on slack? give me a name or #channel.")

        channel_id: Optional[str] = None
        channel_name: str = target
        is_dm = False

        if target.startswith("#"):
            # channel
            chans = await slack_int.list_channels(types="public_channel,private_channel")
            t = target.lstrip("#").lower()
            match = next((c for c in chans if c.name.lower() == t), None)
            if not match:
                return AgentResult(text=f"can't find channel {target}. is ro a member?")
            channel_id = match.channel_id
            channel_name = f"#{match.name}"
        else:
            user = await slack_int.find_user_by_name(target)
            if not user:
                return AgentResult(text=f"can't find a slack user matching '{target}'.")
            channel_id = await slack_int.open_dm(user.user_id)
            channel_name = user.real_name or user.name
            is_dm = True

        # draft body in ro's voice
        profile = await get_profile_body()
        sys = await _voice_for("slack")
        if profile.strip():
            sys += "\n\n## ro's profile\n\n" + profile.strip()
        sys += "\n\nthis message is for SLACK. keep it short. one-line replies are fine. no signoff."

        prompt = f"ro's instruction: {user_text}\n\nrecipient: {channel_name}\n\nwrite the message body only."
        try:
            body = await self._ask(
                system=sys,
                messages=[{"role": "user", "content": prompt}],
                model=settings.model_default,
                max_tokens=400,
                temperature=0.6,
            )
        except Exception as e:
            return AgentResult(text="", error=f"slack draft failed: {e}")

        if not body.strip():
            return AgentResult(text="(no draft produced)")

        action_id = await approval.open_approval(
            session_id=uuid.UUID(session_id),
            domain="comms",
            tool="slack.post_message",
            description=f"slack {'dm' if is_dm else 'message'} to {channel_name}",
            payload={
                "channel_id": channel_id,
                "channel_name": channel_name,
                "is_dm": is_dm,
                "body": body,
            },
            requires_approval=True,
        )

        return AgentResult(
            text=f"drafted a slack {'dm' if is_dm else 'message'} to {channel_name}:\n\n{body}",
            actions_opened=[str(action_id)],
            tool_calls=[{
                "tool": "slack.draft",
                "args": {"to": channel_name, "channel_id": channel_id, "is_dm": is_dm},
                "result": {
                    "channel_name": channel_name,
                    "channel_id": channel_id,
                    "is_dm": is_dm,
                    "body": body,
                },
            }],
        )

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
            return {"intent": "other", "query": "", "target": ""}


def _query_from_text(t: str) -> str:
    """fallback search query if claude didn't give us one."""
    t = t.lower()
    if "unread" in t:
        return "is:unread"
    if "today" in t:
        return "newer_than:1d"
    if "this week" in t or "recent" in t:
        return "newer_than:7d"
    m = re.search(r"from\s+(\w+)", t)
    if m:
        return f"from:{m.group(1)}"
    return "newer_than:7d"


def _split_subject(raw: str) -> tuple[str, str]:
    lines = raw.strip().splitlines()
    if lines and lines[0].lower().startswith("subject:"):
        subject = lines[0].split(":", 1)[1].strip()
        body = "\n".join(lines[1:]).lstrip("\n")
        return (subject or "(no subject)", body)
    return ("(no subject)", raw.strip())


comms_agent = CommsAgent(name="comms", system_prompt=VOICE)
