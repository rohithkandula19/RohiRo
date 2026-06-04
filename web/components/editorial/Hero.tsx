"use client";

import { useCommandPalette } from "@/components/nav/CommandPaletteProvider";
import Link from "next/link";

export function Hero() {
  const palette = useCommandPalette();
  return (
    <div className="card p-6">
      <div className="flex items-center gap-2 text-[11px] text-ink-subtle">
        <span className="dot dot-live" />
        <span>ro is online</span>
        <span>·</span>
        <span>last synced 12s ago</span>
      </div>

      <h2 className="mt-3 text-[20px] font-semibold leading-tight text-ink">
        Good afternoon, Rohith.
      </h2>
      <p className="mt-1 text-[13px] leading-6 text-ink-muted">
        3 drafts need your review, 1 meeting in 2 hours, and a fix waiting on
        approval in rohflow.
      </p>

      <div className="mt-5 flex flex-wrap items-center gap-2">
        <button onClick={() => palette.open()} className="btn btn-primary">
          Ask ro anything
          <kbd className="border-white/30 bg-white/10 text-white/80">⌘K</kbd>
        </button>
        <Link href="/inbox" className="btn">
          Review drafts
        </Link>
      </div>
    </div>
  );
}
