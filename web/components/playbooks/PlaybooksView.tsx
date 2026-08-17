"use client";

import { useCallback, useEffect, useState } from "react";

type Meta = { name: string; title: string; steps: number };
type RunResult = {
  name: string;
  ran: boolean;
  reason?: string;
  completed?: number;
  total?: number;
  steps?: { step: number; ok: boolean; text?: string; error?: string }[];
};

export function PlaybooksView() {
  const [list, setList] = useState<Meta[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [body, setBody] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<RunResult | null>(null);
  const [note, setNote] = useState("");

  const refresh = useCallback(() => {
    fetch("/api/playbooks").then((r) => r.json()).then(setList).catch(() => null);
  }, []);

  useEffect(() => refresh(), [refresh]);

  async function open(n: string) {
    const r = await fetch(`/api/playbooks/${n}`);
    if (!r.ok) return;
    const data = await r.json();
    setSelected(n);
    setName(n);
    setBody(data.body);
    setResult(null);
    setNote("");
  }

  function fresh() {
    setSelected(null);
    setName("");
    setBody("# my playbook\n\n## step one\ndescribe the first thing ro should do.\n\n## step two\nusing the context above, describe the next thing.\n");
    setResult(null);
    setNote("");
  }

  async function save() {
    if (!name.trim()) {
      setNote("name it first (lowercase slug).");
      return;
    }
    setBusy(true);
    const r = await fetch(`/api/playbooks/${name.trim()}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body }),
    });
    setBusy(false);
    setNote(r.ok ? "saved." : `save failed: ${(await r.json()).detail || r.status}`);
    if (r.ok) {
      setSelected(name.trim());
      refresh();
    }
  }

  async function run() {
    if (!selected) return;
    setBusy(true);
    setResult(null);
    setNote("running…");
    const r = await fetch(`/api/playbooks/${selected}/run`, { method: "POST" });
    setBusy(false);
    if (!r.ok) {
      setNote(`run failed: ${r.status}`);
      return;
    }
    setNote("");
    setResult(await r.json());
  }

  async function remove() {
    if (!selected) return;
    await fetch(`/api/playbooks/${selected}`, { method: "DELETE" });
    fresh();
    refresh();
  }

  return (
    <div className="grid max-w-5xl grid-cols-1 gap-4 md:grid-cols-[240px_1fr]">
      <div className="flex flex-col gap-2">
        <button className="btn" onClick={fresh}>new playbook</button>
        {list.map((p) => (
          <button
            key={p.name}
            onClick={() => open(p.name)}
            className={`card text-left text-[13px] ${selected === p.name ? "ring-1 ring-ink" : ""}`}
          >
            <div className="text-ink">{p.name}</div>
            <div className="text-[12px] text-ink-muted">{p.steps} step{p.steps === 1 ? "" : "s"}</div>
          </button>
        ))}
        {list.length === 0 && (
          <div className="text-[12px] text-ink-muted">nothing saved yet.</div>
        )}
      </div>

      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-"))}
            placeholder="playbook-name"
            className="card w-56 text-[13px]"
          />
          <button className="btn" onClick={save} disabled={busy}>save</button>
          <button className="btn" onClick={run} disabled={busy || !selected}>run now</button>
          {selected && (
            <button className="btn" onClick={remove} disabled={busy}>delete</button>
          )}
          <span className="text-[12px] text-ink-muted">{note}</span>
        </div>
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          spellCheck={false}
          className="card min-h-[320px] w-full font-mono text-[13px] leading-5"
        />
        <div className="text-[12px] text-ink-muted">
          schedule it: create a schedule whose text is <code>playbook:{name || "<name>"}</code>. outward writes still stop at approvals.
        </div>
        {result && (
          <div className="card text-[13px]">
            <div className="text-ink">
              {result.ran
                ? `ran ${result.completed}/${result.total} steps`
                : `did not run: ${result.reason}`}
            </div>
            {(result.steps || []).map((s) => (
              <div key={s.step} className="mt-2 border-t border-ink-faint pt-2">
                <div className="text-[12px] text-ink-muted">step {s.step} — {s.ok ? "ok" : "failed"}</div>
                <div className="whitespace-pre-wrap text-[12.5px]">{s.text || s.error}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
