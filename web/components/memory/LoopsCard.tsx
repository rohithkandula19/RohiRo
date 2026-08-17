"use client";

import { useCallback, useEffect, useState } from "react";

type Loop = {
  id: string;
  direction: string;
  who: string;
  what: string;
  due_hint: string;
  age_days: number;
};

export function LoopsCard() {
  const [loops, setLoops] = useState<Loop[]>([]);

  const refresh = useCallback(() => {
    fetch("/api/memory/loops").then((r) => r.json()).then(setLoops).catch(() => null);
  }, []);

  useEffect(() => refresh(), [refresh]);

  async function resolve(id: string, status: "done" | "dropped") {
    await fetch(`/api/memory/loops/${id}/resolve?status=${status}`, { method: "POST" });
    refresh();
  }

  return (
    <div className="card max-w-3xl">
      <div className="text-[13px] text-ink">open loops</div>
      <div className="text-[12px] text-ink-muted">
        promises mined from your sent messages, both directions. they age here until closed.
      </div>
      <div className="mt-2 flex flex-col gap-1">
        {loops.map((l) => (
          <div key={l.id} className="flex items-center justify-between border-t border-ink-faint py-1.5">
            <span className="text-[12.5px]">
              <span className="text-ink-subtle">[{l.direction}]</span>{" "}
              {l.who && <span className="text-ink-muted">{l.who}: </span>}
              <span className="text-ink">{l.what}</span>
              {l.due_hint && <span className="text-ink-muted"> — {l.due_hint}</span>}
              <span className="text-ink-subtle"> · {l.age_days}d</span>
            </span>
            <span className="flex gap-2">
              <button className="btn text-[12px]" onClick={() => resolve(l.id, "done")}>done</button>
              <button className="btn text-[12px]" onClick={() => resolve(l.id, "dropped")}>drop</button>
            </span>
          </div>
        ))}
        {loops.length === 0 && (
          <div className="mt-1 text-[12px] text-ink-muted">nothing open. loops appear after the nightly mine.</div>
        )}
      </div>
    </div>
  );
}
