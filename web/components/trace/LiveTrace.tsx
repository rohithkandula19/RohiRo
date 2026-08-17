"use client";

import { useEffect, useRef, useState } from "react";
import { useEventStream } from "@/lib/sse";

type TraceEvent =
  | { type: "stage"; name: string; text: string }
  | { type: "trace"; kind: string; [k: string]: unknown }
  | { type: "final"; text: string; elapsed_ms: number; domains: string[] };

type Line = { at: string; label: string };

export function LiveTrace() {
  const { last, open } = useEventStream<TraceEvent>("/api/trace/stream", "trace");
  const [lines, setLines] = useState<Line[]>([]);
  const seen = useRef(0);

  // real events only. the log grows as the supervisor actually works.
  useEffect(() => {
    if (!last) return;
    seen.current += 1;
    const label =
      "text" in last && typeof last.text === "string" && last.text
        ? last.text
        : "name" in last && typeof (last as { name?: string }).name === "string"
          ? String((last as { name?: string }).name)
          : "kind" in last
            ? String((last as { kind?: string }).kind)
            : "event";
    const at = new Date().toLocaleTimeString([], { hour12: false });
    setLines((prev) => [...prev.slice(-11), { at, label: label.slice(0, 80) }]);
  }, [last]);

  return (
    <div className="card flex h-full flex-col p-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={"dot" + (open ? " dot-live" : "")} />
          <span className="text-[12.5px] font-medium text-ink">Live trace</span>
        </div>
        <span className="label">{open ? "streaming" : "idle"}</span>
      </div>

      {lines.length === 0 ? (
        <div className="mt-4 flex flex-1 flex-col items-start justify-center gap-1.5">
          <div className="text-[13px] text-ink-muted">Quiet. Nothing is running right now.</div>
          <div className="text-[12px] leading-5 text-ink-subtle">
            When ro works — a message arrives, a routine fires, a bot runs —
            every step of its thinking streams here in real time.
          </div>
        </div>
      ) : (
        <div className="mt-4 space-y-2 text-[12px]">
          {lines.map((l, i) => (
            <div key={i} className="flex items-center gap-3">
              <span className="font-mono text-[10.5px] text-ink-subtle">{l.at}</span>
              <span className={"flex-1 " + (i === lines.length - 1 ? "text-ink" : "text-ink-muted")}>
                {l.label}
              </span>
              {i === lines.length - 1 ? (
                <span className="chip chip-accent">now</span>
              ) : (
                <span className="chip chip-ok">done</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
