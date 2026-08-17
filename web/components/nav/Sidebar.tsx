"use client";

import { useEffect, useState } from "react";

type Conversation = { id: string; title: string; ago: string };

function ago(iso: string | null): string {
  if (!iso) return "";
  const mins = Math.max(0, (Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 60) return `${Math.round(mins)}m`;
  if (mins < 60 * 24) return `${Math.round(mins / 60)}h`;
  return `${Math.round(mins / (60 * 24))}d`;
}

export function Sidebar() {
  const [recent, setRecent] = useState<Conversation[]>([]);

  useEffect(() => {
    // real sessions only. an empty list is the honest empty state.
    fetch("/api/chat/sessions?limit=8")
      .then((r) => r.json())
      .then((rows: { session_id: string; channel: string; chat_key: string; last_at: string | null; turns: number }[]) =>
        setRecent(
          rows
            .filter((r) => r.turns > 0)
            .map((r) => ({
              id: r.session_id,
              title: `${r.channel} · ${r.chat_key.slice(0, 26)}`,
              ago: ago(r.last_at),
            }))
        )
      )
      .catch(() => setRecent([]));
  }, []);

  function newChat() {
    if (typeof window !== "undefined") window.location.href = "/";
  }

  return (
    <aside className="sticky top-0 flex h-screen w-[252px] shrink-0 flex-col border-r border-line bg-sidebar">
      <div className="flex items-center gap-2 px-4 pt-4 pb-3">
        <div className="flex h-7 w-7 items-center justify-center rounded-[7px] bg-accent text-[13px] font-semibold text-accent-ink">
          r
        </div>
        <div className="flex-1">
          <div className="text-[13px] font-semibold text-ink">ro</div>
          <div className="text-[11px] text-ink-subtle">your agent</div>
        </div>
      </div>

      <button
        onClick={newChat}
        className="mx-3 mb-4 flex items-center justify-center gap-2 rounded-[8px] border border-line bg-surface px-3 py-2 text-[13px] font-medium text-ink hover:border-line-strong hover:bg-surface-hover"
      >
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <path d="M12 5v14M5 12h14" />
        </svg>
        New chat
      </button>

      <div className="flex-1 overflow-y-auto px-2 pb-3">
        <div className="px-2 pb-1.5 text-[10.5px] font-medium uppercase tracking-wider text-ink-subtle">
          Recent
        </div>
        <ul className="space-y-px">
          {recent.map((c) => (
            <li key={c.id}>
              <button className="flex w-full items-start gap-2 rounded-[6px] px-2 py-1.5 text-left text-[12.5px] text-ink-muted hover:bg-surface-hover hover:text-ink">
                <span className="line-clamp-1 flex-1">{c.title}</span>
                <span className="shrink-0 text-[10.5px] text-ink-subtle">{c.ago}</span>
              </button>
            </li>
          ))}
          {recent.length === 0 && (
            <li className="px-2 py-1.5 text-[11.5px] text-ink-subtle">
              nothing yet. your first conversation lands here.
            </li>
          )}
        </ul>
      </div>

      <div className="border-t border-line px-3 py-3">
        <div className="flex items-center gap-2 px-2 text-[11px] text-ink-subtle">
          <span className="h-1.5 w-1.5 rounded-full bg-success" />
          <span>ro is online</span>
        </div>
        <button className="mt-2 flex w-full items-center gap-2 rounded-[6px] px-2 py-1.5 text-[12.5px] text-ink-muted hover:bg-surface-hover hover:text-ink">
          <span className="text-ink-subtle">⚙</span>
          <span>Settings</span>
        </button>
      </div>
    </aside>
  );
}
