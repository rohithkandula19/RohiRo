"""voice learner.

every time you approve/reject/edit a draft, a row lands in voice_signals.
the learner periodically takes the last N edits per channel, asks claude
"ro wrote A, you changed it to B — what's the pattern", and writes a few
one-line tone rules to learned_voice. agents read those at runtime.

cheap. runs hourly. no-op when nothing's pending.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from api.config import settings
from api.memory.db import db
from api.observability.claude import claude_client
from api.observability.logging import log

LEARN_SYSTEM = """you are ro's voice analyst.

look at pairs of (what ro drafted, what the user changed it to). figure out the
PATTERN the user keeps applying. output 3-7 short rules in markdown bullets.
each rule must be:
  - concrete and actionable (something an llm writing the next draft can follow)
  - short (one line, <120 chars)
  - phrased as an instruction ("use X", "avoid Y", "open with Z")

do NOT include:
  - generic advice ("be clear", "be polite")
  - rules that only apply to one specific email/thread
  - rules about content topic; only about voice/tone/structure/style

if signals are too few or contradictory, output the single line:
  - (not enough signal yet)
"""


# ----- channel inference -----


def _channel_for(tool: str) -> str:
    if tool.startswith("gmail."):
        return "gmail"
    if tool.startswith("slack."):
        return "slack"
    if tool.startswith("imessage."):
        return "imessage"
    if tool.startswith("calendar."):
        return "calendar"
    if tool in ("shell.run", "file.write", "web.fetch"):
        return "actions"
    return "other"


# ----- capture (called by approval.decide) -----


async def capture_decision(
    *,
    action_id: uuid.UUID,
    tool: str,
    decision: str,
    payload: dict[str, Any],
    edit_note: Optional[str],
) -> None:
    """write a voice_signals row. cheap; called inline from approval.decide."""
    channel = _channel_for(tool)
    original = (payload.get("body") or payload.get("content") or payload.get("command") or "")
    edited = (edit_note or "") if decision == "edited" else (original if decision == "approved" else "")

    await db.execute(
        """insert into voice_signals (action_id, tool, channel, decision, original, edited)
           values ($1, $2, $3, $4, $5, $6)""",
        action_id, tool, channel, decision, str(original)[:4000], str(edited)[:4000],
    )


# ----- learner -----


async def learn_voice(min_signals: int = 4) -> dict[str, Any]:
    """re-derive learned_voice for every channel that has new edit signals."""
    channels = await db.fetch(
        """select channel, count(*) as n
           from voice_signals
           where decision in ('edited','rejected')
           group by channel
           having count(*) >= $1""",
        min_signals,
    )
    out: dict[str, int] = {}
    for row in channels:
        ch = row["channel"]
        n = await _learn_one(ch)
        out[ch] = n
    return out


async def _learn_one(channel: str) -> int:
    sigs = await db.fetch(
        """select decision, original, edited
           from voice_signals
           where channel = $1 and decision in ('edited','rejected')
           order by created_at desc
           limit 30""",
        channel,
    )
    if len(sigs) < 4:
        return 0

    pairs = []
    for s in sigs:
        if s["decision"] == "edited" and s["original"] and s["edited"]:
            pairs.append(f"- DRAFT: {s['original'][:600]}\n  USER WROTE INSTEAD: {s['edited'][:600]}")
        elif s["decision"] == "rejected" and s["original"]:
            pairs.append(f"- DRAFT (rejected outright): {s['original'][:600]}")
    if not pairs:
        return 0

    user_msg = (
        f"channel: {channel}\n"
        f"signals (most recent first):\n\n" +
        "\n\n".join(pairs)
    )
    try:
        resp = await claude_client.message(
            model=settings.model_default,
            system=LEARN_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=500,
            temperature=0.2,
        )
        rules = "".join(b.text for b in resp.content if b.type == "text").strip()
    except Exception:
        log.exception("voice learner failed", channel=channel)
        return 0

    await db.execute(
        """insert into learned_voice (channel, rules_md, n_signals, updated_at)
           values ($1, $2, $3, now())
           on conflict (channel) do update set
             rules_md = excluded.rules_md,
             n_signals = excluded.n_signals,
             updated_at = now()""",
        channel, rules, len(sigs),
    )
    return len(sigs)


# ----- runtime injection -----


async def load_voice(channel: str) -> str:
    """one-line cached lookup. agents call this when building their system prompt."""
    row = await db.fetchrow(
        "select rules_md, n_signals from learned_voice where channel = $1",
        channel,
    )
    if not row or not row["rules_md"]:
        return ""
    return row["rules_md"]
