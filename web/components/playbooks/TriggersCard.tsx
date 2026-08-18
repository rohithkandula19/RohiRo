"use client";

import { useCallback, useEffect, useState } from "react";

type Trigger = {
  id: string;
  channel: string;
  pattern: string;
  playbook: string;
  enabled: boolean;
  fire_count: number;
};

export function TriggersCard() {
  const [list, setList] = useState<Trigger[]>([]);
  const [channel, setChannel] = useState("*");
  const [pattern, setPattern] = useState("");
  const [playbook, setPlaybook] = useState("");
  const [note, setNote] = useState("");

  const refresh = useCallback(() => {
    fetch("/api/triggers").then((r) => r.json()).then(setList).catch(() => null);
  }, []);

  useEffect(() => refresh(), [refresh]);

  async function add() {
    const r = await fetch("/api/triggers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ channel, pattern, playbook }),
    });
    if (!r.ok) {
      setNote((await r.json()).detail || "failed");
      return;
    }
    setNote("");
    setPattern("");
    refresh();
  }

  async function toggle(t: Trigger) {
    await fetch(`/api/triggers/${t.id}/enabled`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: !t.enabled }),
    });
    refresh();
  }

  async function remove(t: Trigger) {
    await fetch(`/api/triggers/${t.id}`, { method: "DELETE" });
    refresh();
  }

  return (
    <div className="card mt-6 max-w-5xl">
      <div className="text-[13px] text-ink">triggers</div>
      <div className="text-[12px] text-ink-muted">
        when a message matching the pattern arrives on a channel, the playbook runs. substring match, or /regex/.
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <select value={channel} onChange={(e) => setChannel(e.target.value)} className="card text-[13px]">
          <option value="*">any channel</option>
          <option value="imessage">imessage</option>
          <option value="telegram">telegram</option>
          <option value="email">email</option>
          <option value="whatsapp">whatsapp</option>
        </select>
        <input
          value={pattern}
          onChange={(e) => setPattern(e.target.value)}
          placeholder="pattern, e.g. invoice"
          className="card w-56 text-[13px]"
        />
        <input
          value={playbook}
          onChange={(e) => setPlaybook(e.target.value.toLowerCase())}
          placeholder="playbook-name"
          className="card w-48 text-[13px]"
        />
        <button className="btn" onClick={add}>add trigger</button>
        <span className="text-[12px] text-danger">{note}</span>
      </div>
      <div className="mt-3 flex flex-col gap-1">
        {list.map((t) => (
          <div key={t.id} className="flex items-center justify-between border-t border-ink-faint py-1.5">
            <span className="text-[12.5px] text-ink">
              {t.channel} · “{t.pattern}” → {t.playbook}
              <span className="text-ink-muted"> · fired {t.fire_count}×</span>
            </span>
            <span className="flex gap-2">
              <button className="btn text-[12px]" onClick={() => toggle(t)}>
                {t.enabled ? "disable" : "enable"}
              </button>
              <button className="btn text-[12px]" onClick={() => remove(t)}>delete</button>
            </span>
          </div>
        ))}
        {list.length === 0 && <div className="text-[12px] text-ink-muted mt-2">no triggers yet.</div>}
      </div>
    </div>
  );
}
