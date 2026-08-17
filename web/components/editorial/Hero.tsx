"use client";

import { useEffect, useState } from "react";
import { useCommandPalette } from "@/components/nav/CommandPaletteProvider";
import Link from "next/link";

function greeting(): string {
  const h = new Date().getHours();
  if (h < 5) return "Up late";
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

export function Hero() {
  const palette = useCommandPalette();
  const [pending, setPending] = useState<number | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => {
    fetch("/api/approvals")
      .then((r) => r.json())
      .then((rows) => setPending(Array.isArray(rows) ? rows.length : 0))
      .catch(() => setPending(null));
    fetch("/health")
      .then((r) => setOnline(r.ok))
      .catch(() => setOnline(false));
  }, []);

  // real state only. no fiction: unknown reads as unknown.
  const summary =
    pending === null
      ? "checking what's waiting on you…"
      : pending === 0
        ? "Nothing is waiting on your approval. Ask for something, or let the routines run."
        : `${pending} action${pending === 1 ? "" : "s"} waiting on your yes.`;

  return (
    <div className="card p-6">
      <div className="flex items-center gap-2 text-[11px] text-ink-subtle">
        <span className={`dot ${online ? "dot-live" : ""}`} />
        <span>{online === null ? "checking…" : online ? "ro is online" : "api not reachable"}</span>
      </div>

      <h2 className="mt-3 text-[20px] font-semibold leading-tight text-ink">
        {greeting()}.
      </h2>
      <p className="mt-1 text-[13px] leading-6 text-ink-muted">{summary}</p>

      <div className="mt-5 flex flex-wrap items-center gap-2">
        <button onClick={() => palette.open()} className="btn btn-primary">
          Ask ro anything
          <kbd className="border-white/30 bg-white/10 text-white/80">⌘K</kbd>
        </button>
        <Link href="/inbox" className="btn">
          Review approvals
        </Link>
      </div>
    </div>
  );
}
