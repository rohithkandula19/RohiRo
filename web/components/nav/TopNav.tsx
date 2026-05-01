"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useCommandPalette } from "@/components/nav/CommandPaletteProvider";

const NAV = [
  { href: "/overview", label: "overview" },
  { href: "/inbox", label: "inbox" },
  { href: "/calendar", label: "calendar" },
  { href: "/code", label: "code" },
  { href: "/jobs", label: "jobs" },
  { href: "/research", label: "research" },
  { href: "/memory", label: "memory" },
  { href: "/files", label: "files" },
  { href: "/health", label: "health" },
  { href: "/finance", label: "finance" },
  { href: "/settings", label: "settings" },
];

export function TopNav() {
  const pathname = usePathname();
  const palette = useCommandPalette();

  return (
    <nav className="sticky top-0 z-30 border-b border-hair border-line bg-surface">
      <div className="mx-auto flex h-16 max-w-[1200px] items-center gap-6 px-6">
        <Link href="/overview" className="flex items-center gap-2">
          <div className="h-5 w-5 rounded-sm bg-accent" />
          <span className="font-serif text-lg leading-none">ro</span>
        </Link>

        <div className="no-scrollbar flex flex-1 items-center gap-1 overflow-x-auto md:gap-3">
          {NAV.map((n) => {
            const active = pathname === n.href || pathname.startsWith(n.href + "/");
            return (
              <Link
                key={n.href}
                href={n.href}
                className={cn(
                  "whitespace-nowrap px-2 py-1 text-[13px] transition-colors",
                  active
                    ? "text-accent border-b-[1.5px] border-accent"
                    : "text-ink-muted hover:text-ink",
                )}
              >
                {n.label}
              </Link>
            );
          })}
        </div>

        <button
          onClick={() => palette.open()}
          className="hidden items-center gap-2 rounded-button border border-hair border-line px-3 py-1.5 text-[12px] text-ink-muted hover:bg-accent-soft md:flex"
          aria-label="open command palette"
        >
          <span>talk to ro</span>
          <kbd className="font-mono text-[10px] text-ink-subtle">⌘K</kbd>
        </button>

        <span className="live-pill" aria-label="live">
          <span className="dot" />
          live
        </span>
      </div>
    </nav>
  );
}
