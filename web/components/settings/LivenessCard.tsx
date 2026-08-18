"use client";

import { useEffect, useState } from "react";

type Beat = { name: string; ok: boolean; error: string; beat_at: string | null };
type Spend = {
  today: { tokens: number; calls: number };
  by_run: { run_label: string; tokens: number; calls: number }[];
  daily_cap: number | null;
};

const STALE_MS = 5 * 60 * 1000;

export function LivenessCard() {
  const [beats, setBeats] = useState<Beat[]>([]);
  const [spend, setSpend] = useState<Spend | null>(null);

  useEffect(() => {
    const load = () => {
      fetch("/api/settings/liveness").then((r) => r.json()).then(setBeats).catch(() => null);
      fetch("/api/settings/spend").then((r) => r.json()).then(setSpend).catch(() => null);
    };
    load();
    const t = setInterval(load, 30_000);
    return () => clearInterval(t);
  }, []);

  const stale = (b: Beat) =>
    !b.beat_at || Date.now() - new Date(b.beat_at).getTime() > STALE_MS;

  return (
    <div className="card max-w-2xl">
      {beats.length === 0 && (
        <div className="text-[12px] text-ink-muted">no heartbeats yet. workers beat once they start.</div>
      )}
      <div className="flex flex-col gap-2">
        {beats.map((b) => {
          const red = !b.ok || stale(b);
          return (
            <div key={b.name} className="flex items-center justify-between">
              <span className="text-[13px] text-ink">{b.name.replace(/_/g, " ")}</span>
              <span className={`text-[12px] ${red ? "text-danger" : "text-success"}`}>
                {red ? (b.error ? `red — ${b.error.slice(0, 60)}` : "stale") : "ok"}
              </span>
            </div>
          );
        })}
      </div>
      {spend && (
        <div className="mt-3 border-t border-ink-faint pt-2 text-[12px] text-ink-muted">
          today: {spend.today.tokens.toLocaleString()} tokens / {spend.today.calls} calls
          {spend.daily_cap ? ` · cap ${Number(spend.daily_cap).toLocaleString()}` : " · no cap set"}
        </div>
      )}
    </div>
  );
}
