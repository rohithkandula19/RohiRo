"use client";

import { useCallback, useEffect, useState } from "react";

type Session = {
  channel: string;
  chat_key: string;
  session_id: string;
  turns: number;
  last_at: string | null;
};

type Event =
  | { kind: "turn"; role: string; body: string; vault: boolean; at: string }
  | { kind: "action"; tool: string; description: string; status: string; at: string };

export function ThreadsView() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [events, setEvents] = useState<Event[]>([]);

  const refresh = useCallback(() => {
    fetch("/api/chat/sessions").then((r) => r.json()).then(setSessions).catch(() => null);
  }, []);

  useEffect(() => refresh(), [refresh]);

  async function open(sid: string) {
    setSelected(sid);
    const r = await fetch(`/api/chat/sessions/${sid}/transcript`);
    if (r.ok) setEvents(await r.json());
  }

  return (
    <div className="grid max-w-5xl grid-cols-1 gap-4 md:grid-cols-[260px_1fr]">
      <div className="flex flex-col gap-2">
        {sessions.map((s) => (
          <button
            key={s.session_id}
            onClick={() => open(s.session_id)}
            className={`card text-left ${selected === s.session_id ? "ring-1 ring-accent" : ""}`}
          >
            <div className="text-[13px] text-ink">
              {s.channel} · {s.chat_key.slice(0, 24)}
            </div>
            <div className="text-[12px] text-ink-muted">
              {s.turns} turns{s.last_at ? ` · ${new Date(s.last_at).toLocaleDateString()}` : ""}
            </div>
          </button>
        ))}
        {sessions.length === 0 && (
          <div className="text-[12px] text-ink-muted">
            no threads yet. every channel conversation lands here.
          </div>
        )}
      </div>
      <div className="flex flex-col gap-2">
        {!selected && <div className="text-[12px] text-ink-muted">pick a thread.</div>}
        {events.map((e, i) =>
          e.kind === "turn" ? (
            <div
              key={i}
              className={`card max-w-[85%] ${e.role === "user" ? "self-end" : "self-start"}`}
            >
              <div className="text-[11px] text-ink-subtle">
                {e.role}
                {e.vault ? " · vault" : ""} · {new Date(e.at).toLocaleTimeString()}
              </div>
              <div className="whitespace-pre-wrap text-[13px]">{e.body}</div>
            </div>
          ) : (
            <div key={i} className="self-center text-[11.5px] text-ink-muted">
              ⚙ {e.tool} — {e.description.slice(0, 90)} · {e.status}
            </div>
          )
        )}
      </div>
    </div>
  );
}
