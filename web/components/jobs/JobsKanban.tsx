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
        <div key={col} className="card min-h-[260px]">
          <div className="kicker">{col}</div>
          <div className="mt-3 space-y-2">
            {(board[col] ?? []).map((a) => (
              <div key={a.id} className="rounded-button border border-hair border-line-subtle p-2">
                <div className="text-[13px] text-ink">{a.company}</div>
                <div className="text-[12px] text-ink-muted">{a.role}</div>
                <div className="kicker mt-1">score {(a.score * 100).toFixed(0)}</div>
                <div className="mt-1 text-[11.5px] text-ink-subtle">{a.next}</div>
              </div>
            ))}
            {!board[col]?.length ? (
              <div className="text-[12px] text-ink-subtle">empty</div>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  );
}
