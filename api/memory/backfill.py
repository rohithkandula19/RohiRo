"""total recall backfill. lifetime corpus, no retention limits, all local.

ingests full history into archive_messages (postgres fts; embeddings are
not required — hybrid search degrades to bm25, and airgap/vault text never
gets embedded anyway):

- imessage: every message in chat.db, watermarked by rowid, resumable.
- gmail: year-windowed sweeps via the existing search + thread reader.
- conversations: the consolidation loop archives raw turns here instead of
  deleting them (summaries stay in conversations for retrieval).

vault taint: rows whose counterparty matches the vault rules are archived
with vault=true and only surface in vault-lane queries.

run:
  uv run python -m api.memory.backfill --imessage
  uv run python -m api.memory.backfill --gmail-years 3
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from api.memory.db import db
from api.observability.logging import log, setup_logging

BATCH = 2000


async def _vault_for(contact_key: str, sender: str) -> bool:
    from api.observability import lanes
    rules = await lanes.vault_rules()
    hay = f"{contact_key} {sender}".lower()
    return any(n and n in hay for n in rules["contacts"] + rules["addresses"])


async def _get_mark(name: str) -> int:
    row = await db.fetchrow(
        "select external_id from seen_keys where source = $1 order by first_seen_at desc limit 1",
        name,
    )
    if not row:
        return 0
    try:
        return int(row["external_id"].split(":", 1)[1])
    except Exception:
        return 0


async def _set_mark(name: str, value: int) -> None:
    await db.execute(
        "insert into seen_keys (source, external_id) values ($1, $2) on conflict do nothing",
        name, f"mark:{value}",
    )


async def backfill_imessage() -> dict[str, Any]:
    from api.integrations import imessage as imsg
    if not imsg.configured():
        return {"skipped": "chat.db not readable (grant full disk access)"}

    total = 0
    mark = await _get_mark("archive_imessage")
    while True:
        msgs = await imsg.all_messages(since_rowid=mark, limit=BATCH)
        if not msgs:
            break
        for m in msgs:
            vault = await _vault_for(m.from_handle, m.chat_display)
            await db.execute(
                """insert into archive_messages
                   (source, external_id, contact_key, sender, from_me, body, vault, sent_at)
                   values ('imessage', $1, $2, $3, $4, $5, $6, nullif($7,'')::timestamptz)
                   on conflict (source, external_id) do nothing""",
                str(m.rowid), (m.from_handle or m.chat_display)[:200],
                m.chat_display[:200], m.from_me, m.text[:16000], vault, m.sent_at,
            )
            mark = max(mark, m.rowid)
            total += 1
        await _set_mark("archive_imessage", mark)
        log.info("imessage backfill progress", archived=total, rowid=mark)
    return {"archived": total, "watermark": mark}


async def backfill_gmail(years: int = 2) -> dict[str, Any]:
    from api.integrations import gmail
    if not gmail.configured():
        return {"skipped": "gmail not connected"}

    from datetime import datetime, timezone
    total = 0
    year_now = datetime.now(tz=timezone.utc).year
    for year in range(year_now - years + 1, year_now + 1):
        query = f"after:{year}/01/01 before:{year + 1}/01/01"
        try:
            threads = await gmail.search_threads(query, max_results=500)
        except Exception as e:
            log.warning("gmail backfill search failed", year=year, error=str(e))
            continue
        for t in threads:
            try:
                full = await gmail.get_thread(t.thread_id)
            except Exception:
                continue
            for msg in full.messages:
                if not (msg.body or "").strip():
                    continue
                vault = await _vault_for(msg.from_email, " ".join(msg.to))
                await db.execute(
                    """insert into archive_messages
                       (source, external_id, contact_key, sender, from_me, body, vault, sent_at)
                       values ('gmail', $1, $2, $3, $4, $5, $6, null)
                       on conflict (source, external_id) do nothing""",
                    msg.message_id, (msg.from_email or "")[:200], (msg.from_name or "")[:200],
                    False, msg.body[:16000], vault,
                )
                total += 1
        log.info("gmail backfill progress", year=year, archived=total)
    return {"archived": total, "years": years}


async def search_archive(q: str, *, limit: int = 20, vault_visible: bool = False) -> list[dict[str, Any]]:
    rows = await db.fetch(
        """select source, contact_key, sender, from_me, body, sent_at,
                  ts_rank(body_tsv, plainto_tsquery('english', $1)) as score
           from archive_messages
           where body_tsv @@ plainto_tsquery('english', $1)
             and (not vault or $3)
           order by score desc, sent_at desc nulls last
           limit $2""",
        q, limit, vault_visible,
    )
    return [
        {
            "source": r["source"], "contact": r["contact_key"], "sender": r["sender"],
            "from_me": r["from_me"], "body": r["body"][:600],
            "sent_at": r["sent_at"].isoformat() if r["sent_at"] else None,
        }
        for r in rows
    ]


async def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="total recall backfill")
    parser.add_argument("--imessage", action="store_true")
    parser.add_argument("--gmail-years", type=int, default=0)
    args = parser.parse_args()
    if args.imessage:
        print(await backfill_imessage())
    if args.gmail_years:
        print(await backfill_gmail(args.gmail_years))
    if not args.imessage and not args.gmail_years:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
