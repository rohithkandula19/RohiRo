"use client";

import { useEventStream } from "@/lib/sse";

type TraceEvent =
  | { type: "stage"; name: string; text: string }
  | { type: "trace"; kind: string; [k: string]: unknown }
  | { type: "final"; text: string; elapsed_ms: number; domains: string[] };

export function LiveTrace() {
  const { last, open } = useEventStream<TraceEvent>("/api/trace/stream", "trace");

  // dev fallback: if no real event yet, show the example trace
  const stage =
    last && "text" in last && typeof last.text === "string" ? last.text : "drafting reply to sarah";
  const tools = ["gmail.thread", "memory.tone", "calendar.free"];

  return (
    <div className="card flex h-full flex-col">
      <div className="flex items-center justify-between">
        <span className="live-pill">
          <span className="dot" />
          live trace
        </span>
        <span className="kicker">{open ? "connected" : "idle"}</span>
      </div>

      <div className="mt-4 flex items-center gap-2">
        <div className="font-mono text-[11px] uppercase tracking-wider text-ink-muted">
          {stage}
        </div>
        <div className="font-mono text-[11px] text-ink-subtle">· 1.4s</div>
      </div>

      <div className="mt-4 h-[68px] overflow-hidden rounded-[6px] bg-accent-soft">
        <div className="h-full w-[62%] animate-pulse bg-accent/80" />
      </div>

      <div className="mt-5 flex items-center gap-3 rounded-card border border-hair border-line-subtle p-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-accent text-[11px] font-medium text-accent-ink">
          sl
        </div>
        <div className="flex-1">
          <div className="text-[13px] text-ink">sarah lin</div>
          <div className="kicker">recruiter · photon labs</div>
        </div>
        <span className="chip">approve</span>
      </div>

      <div className="mt-4 space-y-2">
        <div className="kicker">draft</div>
        <div className="rounded-card bg-bg p-3 text-[13px] leading-6 text-ink">
          tuesday afternoon works. i&apos;ll block 2 to 3:30 et and send a
          calendar hold. anything specific you want me to dig into beforehand?
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-1.5">
        {tools.map((t) => (
          <span key={t} className="chip">
            {t}
          </span>
        ))}
      </div>
    </div>
  );
}
