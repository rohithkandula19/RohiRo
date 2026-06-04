"use client";

import { useEventStream } from "@/lib/sse";

type TraceEvent =
  | { type: "stage"; name: string; text: string }
  | { type: "trace"; kind: string; [k: string]: unknown }
  | { type: "final"; text: string; elapsed_ms: number; domains: string[] };

export function LiveTrace() {
  const { last, open } = useEventStream<TraceEvent>("/api/trace/stream", "trace");
  const stage = last && "text" in last && typeof last.text === "string" ? last.text : "Drafting reply to Sarah";
  const tools = ["gmail.thread", "memory.tone", "calendar.free"];

  return (
    <div className="card flex h-full flex-col p-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="dot dot-live" />
          <span className="text-[12.5px] font-medium text-ink">Live trace</span>
        </div>
        <span className="label">{open ? "streaming" : "idle"}</span>
      </div>

      <div className="mt-4 space-y-2 text-[12px]">
        <Step time="14:02:18" label="Supervisor intake" />
        <Step time="14:02:19" label="Memory retrieve · 6 hits" />
        <Step time="14:02:19" label="Classify → comms" />
        <Step time="14:02:20" label={stage} active />
      </div>

      <div className="mt-4 rounded-[6px] border border-line bg-surface-hover p-3">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-accent text-[11px] font-semibold text-accent-ink">
            SL
          </div>
          <div className="flex-1">
            <div className="text-[13px] font-medium text-ink">Sarah Lin</div>
            <div className="label">Recruiter · Photon Labs</div>
          </div>
          <span className="chip chip-warn">Approve</span>
        </div>
      </div>

      <div className="mt-4">
        <div className="label mb-1.5">Draft</div>
        <div className="rounded-[6px] border-l-2 border-accent bg-accent-soft px-3 py-2.5 text-[12.5px] leading-6 text-ink">
          Tuesday afternoon works. I&apos;ll block 2 to 3:30 ET and send a calendar
          hold. Anything specific you want me to dig into beforehand?
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {tools.map((t) => (
          <span key={t} className="chip chip-accent">{t}</span>
        ))}
      </div>
    </div>
  );
}

function Step({ time, label, active }: { time: string; label: string; active?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <span className="font-mono text-[10.5px] text-ink-subtle">{time}</span>
      <span className={"flex-1 " + (active ? "text-ink" : "text-ink-muted")}>{label}</span>
      {active ? <span className="chip chip-accent">1.4s</span> : <span className="chip chip-ok">done</span>}
    </div>
  );
}
