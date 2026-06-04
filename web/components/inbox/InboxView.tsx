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
      <div className="flex flex-wrap items-center gap-1.5">
        {SOURCES.map((s) => (
          <button
            key={s}
            onClick={() => setSource(s)}
            className={
              "rounded-[5px] border px-2.5 py-1 text-[12px] capitalize transition-colors " +
              (source === s
                ? "border-accent/30 bg-accent-soft text-accent"
                : "border-line bg-surface text-ink-muted hover:bg-surface-hover")
            }
          >
            {s}
          </button>
        ))}
        <label className="ml-2 flex items-center gap-2 text-[12px] text-ink-muted">
          <input type="checkbox" checked={unread} onChange={(e) => setUnread(e.target.checked)} className="accent-accent" />
          Unread only
        </label>
      </div>

      <div className="mt-4 card overflow-hidden">
        {rows.length === 0 ? (
          <div className="p-6 text-[13px] text-ink-subtle">Inbox is quiet.</div>
        ) : (
          rows.map((r) => (
            <div
              key={r.id}
              className="flex cursor-pointer items-start gap-3 border-b border-line px-4 py-3 last:border-b-0 hover:bg-surface-hover"
            >
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent-soft text-[10.5px] font-semibold text-accent">
                {initials(r.from_name)}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="text-[13px] font-medium text-ink">{r.from_name}</span>
                  <span className="chip capitalize">{r.source}</span>
                  {r.unread ? <span className="dot dot-live" /> : null}
                  {r.has_draft ? <span className="chip chip-warn">Draft</span> : null}
                  <span className="ml-auto text-[11.5px] text-ink-subtle">{formatRelative(r.received_at)}</span>
                </div>
                {r.subject ? <div className="mt-0.5 text-[12.5px] text-ink-muted">{r.subject}</div> : null}
                <div className="mt-0.5 line-clamp-1 text-[12px] text-ink-subtle">{r.snippet}</div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function initials(name: string) {
  return name.split(/\s+/).map((s) => s[0]).filter(Boolean).slice(0, 2).join("").toUpperCase();
}
