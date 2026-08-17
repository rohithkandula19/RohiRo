"use client";

import { useCallback, useEffect, useState } from "react";

type Bot = { name: string; title: string };
type Handoff = { bot: string; text?: string; error?: string };
type RunOut = {
  bot?: string;
  ran?: boolean;
  text?: string;
  error?: string;
  reason?: string;
  handoffs?: Handoff[];
  summary?: string;
  assignments?: { bot: string; task: string }[];
};
type Msg = { from: string; to: string; body: string; at: string };

export function CrewView() {
  const [bots, setBots] = useState<Bot[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [charter, setCharter] = useState("");
  const [name, setName] = useState("");
  const [task, setTask] = useState("");
  const [out, setOut] = useState<RunOut | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");

  const refresh = useCallback(() => {
    fetch("/api/bots").then((r) => r.json()).then(setBots).catch(() => null);
    fetch("/api/bots/messages?limit=40").then((r) => r.json()).then(setMsgs).catch(() => null);
  }, []);

  useEffect(() => refresh(), [refresh]);

  async function open(n: string) {
    const r = await fetch(`/api/bots/${n}`);
    if (!r.ok) return;
    const d = await r.json();
    setSelected(n);
    setName(n);
    setCharter(d.charter);
    setOut(null);
  }

  function fresh() {
    setSelected(null);
    setName("");
    setCharter("# name\none-line mission.\n\n## owns\n\n## how i work\n(delegate with '>> bot: task')\n\n## never\nsend anything outward without approval.\n");
    setOut(null);
  }

  async function hire() {
    const role = window.prompt("describe the role in plain words — what should this bot own and do?");
    if (!role || role.trim().length < 10) return;
    setBusy(true);
    setNote("writing charter…");
    const r = await fetch("/api/bots/draft", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role }),
    });
    setBusy(false);
    setNote(r.ok ? "charter drafted. name it and save." : "draft failed — api key set?");
    if (r.ok) {
      setSelected(null);
      setCharter((await r.json()).charter);
    }
  }

  async function save() {
    if (!name.trim()) { setNote("name it first."); return; }
    const r = await fetch(`/api/bots/${name.trim()}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: charter }),
    });
    setNote(r.ok ? "saved." : "save failed");
    if (r.ok) { setSelected(name.trim()); refresh(); }
  }

  async function runOne() {
    if (!selected || task.trim().length < 3) return;
    setBusy(true); setOut(null); setNote("running…");
    const r = await fetch(`/api/bots/${selected}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task }),
    });
    setBusy(false); setNote("");
    if (r.ok) { setOut(await r.json()); refresh(); }
  }

  async function runCrew() {
    if (task.trim().length < 3) { setNote("type a task first."); return; }
    setBusy(true); setOut(null); setNote("crew planning…");
    const r = await fetch("/api/bots/crew/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task }),
    });
    setBusy(false); setNote("");
    if (r.ok) { setOut(await r.json()); refresh(); }
  }

  return (
    <div className="grid max-w-6xl grid-cols-1 gap-4 md:grid-cols-[240px_1fr_280px]">
      <div className="flex flex-col gap-2">
        <button className="btn" onClick={fresh}>new charter</button>
        <button className="btn" onClick={hire} disabled={busy}>hire from a description</button>
        {bots.map((b) => (
          <button
            key={b.name}
            onClick={() => open(b.name)}
            className={`card text-left ${selected === b.name ? "ring-1 ring-ink" : ""}`}
          >
            <div className="text-[13px] text-ink">{b.name}</div>
            <div className="text-[12px] text-ink-muted">{b.title}</div>
          </button>
        ))}
        {bots.length === 0 && <div className="text-[12px] text-ink-muted">no bots hired yet.</div>}
      </div>

      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-"))}
            placeholder="bot-name"
            className="card w-44 text-[13px]"
          />
          <button className="btn" onClick={save} disabled={busy}>save</button>
          <span className="text-[12px] text-ink-muted">{note}</span>
        </div>
        <textarea
          value={charter}
          onChange={(e) => setCharter(e.target.value)}
          spellCheck={false}
          className="card min-h-[220px] w-full font-mono text-[13px] leading-5"
        />
        <div className="flex items-center gap-2">
          <input
            value={task}
            onChange={(e) => setTask(e.target.value)}
            placeholder="give the crew (or the selected bot) a task…"
            className="card flex-1 text-[13px]"
          />
          <button className="btn" onClick={runOne} disabled={busy || !selected}>run bot</button>
          <button className="btn" onClick={runCrew} disabled={busy}>run crew</button>
        </div>
        {out && (
          <div className="card text-[13px]">
            {out.reason && <div className="text-red-400">{out.reason}</div>}
            {out.assignments && (
              <div className="mb-2 text-[12px] text-ink-muted">
                plan: {out.assignments.map((a) => `${a.bot} ← ${a.task.slice(0, 50)}`).join(" · ")}
              </div>
            )}
            <div className="whitespace-pre-wrap">{out.summary || out.text || out.error}</div>
            {(out.handoffs || []).map((h, i) => (
              <div key={i} className="mt-2 border-t border-ink-faint pt-2">
                <div className="text-[11.5px] text-ink-subtle">↳ {h.bot}</div>
                <div className="whitespace-pre-wrap text-[12.5px]">{(h.text || h.error || "").slice(0, 1200)}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="flex flex-col gap-1">
        <div className="text-[12px] text-ink-muted">handoff log (no hidden channels)</div>
        {msgs.map((m, i) => (
          <div key={i} className="card py-1.5 text-[11.5px]">
            <span className="text-ink">{m.from} → {m.to}</span>
            <div className="text-ink-muted">{m.body.slice(0, 110)}</div>
          </div>
        ))}
        {msgs.length === 0 && <div className="text-[12px] text-ink-subtle">quiet so far.</div>}
      </div>
    </div>
  );
}
