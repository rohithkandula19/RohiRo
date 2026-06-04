"use client";

import { useEffect, useState } from "react";

type App = { id: string; company: string; role: string; score: number; next: string };
type Board = Record<string, App[]>;

const COLS = ["applied", "screen", "onsite", "offer", "rejected"];

export function JobsKanban() {
  const [board, setBoard] = useState<Board>({});
  useEffect(() => {
    fetch("/api/jobs/applications")
      .then((r) => r.json())
      .then(setBoard)
      .catch(() => setBoard({}));
  }, []);

  return (
    <div className="grid gap-3 md:grid-cols-5">
      {COLS.map((col) => (
        <div key={col} className="card min-h-[280px] p-3">
          <div className="mb-2.5 flex items-center justify-between">
            <div className="text-[12px] font-semibold capitalize text-ink">{col}</div>
            <span className="text-[11px] text-ink-subtle">{board[col]?.length ?? 0}</span>
          </div>
          <div className="space-y-2">
            {(board[col] ?? []).map((a) => (
              <div key={a.id} className="rounded-[6px] border border-line bg-surface px-2.5 py-2 hover:bg-surface-hover">
                <div className="text-[12.5px] font-medium text-ink">{a.company}</div>
                <div className="text-[11.5px] text-ink-muted">{a.role}</div>
                <div className="mt-1.5 flex items-center justify-between">
                  <span className="chip chip-accent">{(a.score * 100).toFixed(0)}%</span>
                  <span className="text-[10.5px] text-ink-subtle">{a.next}</span>
                </div>
              </div>
            ))}
            {!board[col]?.length ? <div className="text-[11.5px] text-ink-subtle">—</div> : null}
          </div>
        </div>
      ))}
    </div>
  );
}
