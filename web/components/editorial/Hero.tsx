"use client";

import { useCommandPalette } from "@/components/nav/CommandPaletteProvider";
import Link from "next/link";

export function Hero() {
  const palette = useCommandPalette();
  return (
    <div className="max-w-xl">
      <div className="kicker mb-4">— a personal operating system</div>
      <h1 className="headline text-[44px] md:text-[52px]">
        one agent.
        <br />
        <span className="headline-italic text-ink">your whole life.</span>
      </h1>
      <p className="mt-6 max-w-[360px] text-body text-ink-muted">
        ro reads your email, knows your calendar, watches your repos, drafts
        your replies, and asks before sending anything. it lives on your mac,
        runs on your terms, forgets nothing.
      </p>
      <div className="mt-7 flex items-center gap-3">
        <button onClick={() => palette.open()} className="btn-primary">
          talk to ro
        </button>
        <Link href="/memory" className="btn-secondary">
          see what it knows
        </Link>
      </div>
    </div>
  );
}
