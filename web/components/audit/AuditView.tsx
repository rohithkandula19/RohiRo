"use client";

import { useCallback, useEffect, useState } from "react";

type Entry = {
  id: number;
  basis: string;
  channel: string;
  destination: string;
  payload_sha: string;
  action_id: string | null;
  created_at: string;
};

type Verdict = { ok: boolean; entries?: number; head?: string; broken_at?: number; reason?: string };

export function AuditView() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    fetch("/api/audit").then((r) => r.json()).then(setEntries).catch(() => null);
  }, []);

  useEffect(() => refresh(), [refresh]);

  async function verify() {
    setBusy(true);
    setVerdict(null);
    const r = await fetch("/api/audit/verify");
    setBusy(false);
    if (r.ok) setVerdict(await r.json());
  }

  return (
    <div className="max-w-4xl">
      <div className="card mb-4 flex items-center justify-between">
        <div className="text-[13px] text-ink-muted">
          {entries.length === 0
            ? "no egress yet. the first outward send writes the first receipt."
            : `${entries.length} recent receipts shown.`}
        </div>
        <div className="flex items-center gap-3">
          {verdict && (
            <span className={`text-[12.5px] ${verdict.ok ? "text-success" : "text-danger"}`}>
              {verdict.ok
                ? `chain intact · ${verdict.entries} entries`
                : `BROKEN at #${verdict.broken_at}: ${verdict.reason}`}
            </span>
          )}
          <button className="btn" onClick={verify} disabled={busy}>
            {busy ? "verifying…" : "verify chain"}
          </button>
        </div>
      </div>
      <div className="flex flex-col gap-1">
        {entries.map((e) => (
          <div key={e.id} className="card flex items-center justify-between py-2">
            <div className="text-[12.5px]">
              <span className="text-ink">#{e.id}</span>{" "}
              <span className="text-ink-muted">[{e.basis}]</span>{" "}
              <span className="text-ink">{e.channel}</span>
              <span className="text-ink-muted"> → {e.destination || "(none)"} </span>
            </div>
            <div className="font-mono text-[11px] text-ink-subtle">
              {e.payload_sha.slice(0, 12)}… · {new Date(e.created_at).toLocaleString()}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
