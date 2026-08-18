"use client";

import { useCallback, useEffect, useState } from "react";

type Schedule = {
  id: string;
  kind: string;
  spec: string;
  text: string;
  title: string;
  timezone: string;
  enabled: boolean;
  next_run_at: string;
  last_result: string | null;
};

export function RoutinesCard() {
  const [list, setList] = useState<Schedule[]>([]);
  const [spec, setSpec] = useState("30 7 * * *");
  const [text, setText] = useState("");
  const [note, setNote] = useState("");

  const refresh = useCallback(() => {
    fetch("/api/schedules").then((r) => r.json()).then(setList).catch(() => null);
  }, []);

  useEffect(() => refresh(), [refresh]);

  async function add() {
    if (!text.trim()) { setNote("what should it do? (plain task, playbook:<name>, or bot:<name>: task)"); return; }
    const r = await fetch("/api/schedules", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: "cron", spec, text, title: text.slice(0, 60) }),
    });
    setNote(r.ok ? "" : "failed — check the cron spec");
    if (r.ok) { setText(""); refresh(); }
  }

  async function remove(id: string) {
    await fetch(`/api/schedules/${id}`, { method: "DELETE" });
    refresh();
  }

  async function runNow(id: string) {
    setNote("running…");
    await fetch(`/api/schedules/${id}/run`, { method: "POST" });
    setNote("");
    refresh();
  }

  return (
    <div className="card mt-6 max-w-5xl">
      <div className="text-[13px] text-ink">routines</div>
      <div className="text-[12px] text-ink-muted">
        cron schedules through the supervisor. text can be a plain task, <code>playbook:&lt;name&gt;</code>, or <code>bot:&lt;name&gt;: task</code>.
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <input value={spec} onChange={(e) => setSpec(e.target.value)} className="card w-36 font-mono text-[12.5px]" placeholder="30 7 * * *" />
        <input value={text} onChange={(e) => setText(e.target.value)} className="card flex-1 text-[13px]" placeholder="build my morning digest / playbook:morning-scan / bot:scout: check my competitors" />
        <button className="btn" onClick={add}>schedule</button>
        <span className="text-[12px] text-danger">{note}</span>
      </div>
      <div className="mt-3 flex flex-col gap-1">
        {list.map((s) => (
          <div key={s.id} className="flex items-center justify-between border-t border-ink-faint py-1.5">
            <span className="text-[12.5px]">
              <span className={s.enabled ? "text-ink" : "text-ink-subtle line-through"}>{s.title || s.text}</span>
              <span className="text-ink-muted"> · {s.kind === "cron" ? s.spec : "once"} · next {new Date(s.next_run_at).toLocaleString()}</span>
            </span>
            <span className="flex gap-2">
              <button className="btn text-[12px]" onClick={() => runNow(s.id)}>run now</button>
              <button className="btn text-[12px]" onClick={() => remove(s.id)}>delete</button>
            </span>
          </div>
        ))}
        {list.length === 0 && <div className="mt-1 text-[12px] text-ink-muted">no routines yet.</div>}
      </div>
    </div>
  );
}
