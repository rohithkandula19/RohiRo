"use client";

import { useEffect, useState } from "react";
import { formatRelative } from "@/lib/utils";

type Row = {
  id: string;
  source: string;
  from_name: string;
  from_handle: string;
  subject: string;
  snippet: string;
  received_at: string;
  unread: boolean;
  has_draft: boolean;
};

const SOURCES = ["all", "gmail", "slack", "imessage", "telegram", "whatsapp", "linkedin"];

export function InboxView() {
  const [source, setSource] = useState("all");
  const [unread, setUnread] = useState(false);
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    const params = new URLSearchParams();
    if (source !== "all") params.set("source", source);
    if (unread) params.set("unread_only", "true");
    fetch(`/api/inbox?${params.toString()}`)
      .then((r) => r.json())
      .then(setRows)
      .catch(() => setRows([]));
  }, [source, unread]);

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        {SOURCES.map((s) => (
          <button
            key={s}
            onClick={() => setSource(s)}
            className={
              "rounded-button border border-hair px-3 py-1.5 text-[12px] " +
              (source === s ? "border-accent bg-accent-soft text-accent" : "border-line text-ink-muted")
            }
          >
            {s}
          </button>
        ))}
        <label className="ml-2 flex items-center gap-2 text-[12px] text-ink-muted">
          <input
            type="checkbox"
            checked={unread}
            onChange={(e) => setUnread(e.target.checked)}
          />
          unread only
        </label>
      </div>

      <div className="mt-6 overflow-hidden rounded-card border border-hair border-line">
        {rows.length === 0 ? (
          <div className="p-6 text-[13px] text-ink-subtle">nothing here. either it&apos;s quiet, or the api isn&apos;t up.</div>
        ) : (
          rows.map((r) => (
            <div
              key={r.id}
              className="flex cursor-pointer items-start gap-4 border-b border-hair border-line-subtle bg-surface p-4 last:border-b-0 hover:bg-accent-soft"
            >
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent text-[11px] font-medium text-accent-ink">
                {initials(r.from_name)}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="text-[13.5px] text-ink">{r.from_name}</span>
                  <span className="chip">{r.source}</span>
                  {r.unread ? <span className="h-1.5 w-1.5 rounded-full bg-accent" /> : null}
                  {r.has_draft ? <span className="chip">draft</span> : null}
                  <span className="ml-auto kicker">{formatRelative(r.received_at)}</span>
                </div>
                {r.subject ? <div className="text-[13px] text-ink-muted">{r.subject}</div> : null}
                <div className="mt-1 line-clamp-1 text-[13px] text-ink-subtle">{r.snippet}</div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function initials(name: string) {
  return name
    .split(/\s+/)
    .map((s) => s[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toLowerCase();
}
