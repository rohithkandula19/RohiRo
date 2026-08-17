"use client";

import { useCallback, useEffect, useState } from "react";

type Pending = {
  id: string;
  tool: string;
  description: string;
  payload?: Record<string, unknown>;
};

export function ApprovalsList() {
  const [pending, setPending] = useState<Pending[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  const refresh = useCallback(() => {
    fetch("/api/approvals")
      .then((r) => r.json())
      .then((rows) => setPending(Array.isArray(rows) ? rows : []))
      .catch(() => setPending([]));
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 15_000);
    return () => clearInterval(t);
  }, [refresh]);

  async function decide(id: string, decision: "approved" | "rejected") {
    setBusy(id);
    await fetch(`/api/approvals/${id}/decide`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision }),
    }).catch(() => null);
    setBusy(null);
    refresh();
  }

  if (pending.length === 0) {
    return (
      <div className="card p-4 text-[13px] text-ink-muted">
        Nothing waiting on your approval. When ro wants to send, post, or run
        something, the card appears here (and on your phone).
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {pending.map((p) => (
        <div key={p.id} className="card overflow-hidden">
          <div className="flex items-center justify-between border-b border-line bg-warning/[0.04] px-4 py-2.5">
            <div className="flex items-center gap-2 text-[12px]">
              <span className="chip chip-warn">Approval</span>
              <span className="text-ink-muted">{p.description}</span>
            </div>
            <span className="text-[11px] text-ink-subtle">{p.tool}</span>
          </div>
          <div className="p-4">
            {typeof p.payload?.body === "string" && (
              <div className="rounded-[6px] border-l-2 border-warning bg-surface-hover px-3 py-2.5 text-[13px] leading-6 text-ink whitespace-pre-wrap">
                {String(p.payload.body).slice(0, 1200)}
              </div>
            )}
            <div className="mt-3 flex gap-2">
              <button
                className="btn btn-primary"
                disabled={busy === p.id}
                onClick={() => decide(p.id, "approved")}
              >
                Approve & run
              </button>
              <button
                className="btn btn-danger"
                disabled={busy === p.id}
                onClick={() => decide(p.id, "rejected")}
              >
                Reject
              </button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
