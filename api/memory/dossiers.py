"""relationship register. per-contact dossiers from the whole local corpus.

nightly (called from consolidation): for the most active recent contacts,
join everything you have with that person — archived imessages and email,
open commitments, contact notes — and have claude distill a dossier: who
they are to you, current threads, promises open in both directions, and
the register you actually use with them. drafts to that person inject the
dossier, so replies sound like you-with-them, not a generic assistant.

the join is computable only where all the stores live: on this machine.
vault contacts never get a cloud-written dossier (lane check applies).
"""

from __future__ import annotations

from typing import Any, Optional

from api.config import settings
from api.memory.db import db
from api.observability import budget
from api.observability.claude import claude_client
from api.observability.logging import log

MAX_CONTACTS_PER_NIGHT = 8
EVIDENCE_MESSAGES = 60

DOSSIER_PROMPT = (
    "you are writing a private dossier about the user's relationship with "
    "one person, from message history and commitments. sections: who they "
    "are to the user; active threads right now; open promises (each "
    "direction, with dates if present); how the user talks to them "
    "(register, length, warmth — quote 2 short examples). tight markdown, "
    "under 300 words. no invention: only what the evidence shows."
)


async def _active_contacts(limit: int) -> list[str]:
    rows = await db.fetch(
        """select contact_key, count(*) as n
           from archive_messages
           where sent_at > now() - interval '30 days'
             and not vault and contact_key != ''
           group by contact_key order by n desc limit $1""",
        limit,
    )
    return [r["contact_key"] for r in rows]


async def _evidence(contact_key: str) -> str:
    msgs = await db.fetch(
        """select sender, from_me, body, sent_at from archive_messages
           where contact_key = $1 and not vault
           order by sent_at desc nulls last limit $2""",
        contact_key, EVIDENCE_MESSAGES,
    )
    commits = await db.fetch(
        """select direction, what, due_hint, status from commitments
           where who ilike '%' || $1 || '%' and status = 'open' limit 10""",
        contact_key[:40],
    )
    lines = [
        f"{'me' if m['from_me'] else (m['sender'] or 'them')}: {m['body'][:400]}"
        for m in reversed(list(msgs))
    ]
    if commits:
        lines.append("\nopen commitments:")
        lines += [f"- ({c['direction']}) {c['what']} {c['due_hint']}" for c in commits]
    return "\n".join(lines)


async def build_dossiers() -> dict[str, Any]:
    """nightly build for the most active contacts. key-gated, budget-checked."""
    from api.observability import claude as claude_mod
    if not claude_mod.configured():
        return {"skipped": "no anthropic_api_key"}
    allowed, why = await budget.allow_run("dossiers")
    if not allowed:
        return {"skipped": why}

    budget.set_run("dossiers")
    built = 0
    for contact in await _active_contacts(MAX_CONTACTS_PER_NIGHT):
        evidence = await _evidence(contact)
        if len(evidence) < 200:
            continue
        try:
            resp = await claude_client.message(
                model=settings.model_cheap,
                system=DOSSIER_PROMPT,
                messages=[{"role": "user", "content": evidence[:60_000]}],
                max_tokens=600,
                temperature=0.2,
            )
            md = "".join(b.text for b in resp.content if b.type == "text").strip()
            if not md:
                continue
            await db.execute(
                """insert into contact_dossiers (contact_key, dossier_md, updated_at)
                   values ($1, $2, now())
                   on conflict (contact_key) do update
                   set dossier_md = excluded.dossier_md, updated_at = now()""",
                contact, md,
            )
            built += 1
        except Exception:
            log.exception("dossier build failed", contact=contact)
    return {"built": built}


async def dossier_for(recipient: str) -> Optional[str]:
    """the dossier whose contact key appears in the recipient string."""
    if not recipient.strip():
        return None
    row = await db.fetchrow(
        """select dossier_md from contact_dossiers
           where $1 ilike '%' || contact_key || '%'
              or contact_key ilike '%' || $1 || '%'
           order by updated_at desc limit 1""",
        recipient.strip()[:200],
    )
    return row["dossier_md"] if row else None
