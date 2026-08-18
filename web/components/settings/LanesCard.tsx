"use client";

import { useCallback, useEffect, useState } from "react";

type Rules = { channels: string[]; contacts: string[]; domains: string[]; addresses: string[] };

export function LanesCard() {
  const [airgap, setAirgap] = useState(false);
  const [rules, setRules] = useState<Rules>({ channels: [], contacts: [], domains: [], addresses: [] });
  const [note, setNote] = useState("");

  const refresh = useCallback(() => {
    fetch("/api/settings/lanes")
      .then((r) => r.json())
      .then((d) => {
        setAirgap(!!d.airgap);
        setRules(d.vault_rules);
      })
      .catch(() => null);
  }, []);

  useEffect(() => refresh(), [refresh]);

  async function toggleAirgap() {
    const r = await fetch("/api/settings/lanes/airgap", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ on: !airgap }),
    });
    if (r.ok) setAirgap(!airgap);
  }

  async function saveRules(next: Rules) {
    setRules(next);
    const r = await fetch("/api/settings/lanes/vault", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(next),
    });
    setNote(r.ok ? "saved." : "save failed");
    setTimeout(() => setNote(""), 1500);
  }

  function editor(field: keyof Rules, label: string, hint: string) {
    return (
      <div className="mt-2">
        <div className="text-[12px] text-ink-muted">{label} <span className="text-ink-subtle">({hint})</span></div>
        <input
          className="card mt-1 w-full text-[12.5px]"
          value={rules[field].join(", ")}
          onChange={(e) =>
            setRules({ ...rules, [field]: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })
          }
          onBlur={() => saveRules(rules)}
          placeholder="comma separated"
        />
      </div>
    );
  }

  return (
    <div className="card max-w-2xl">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[13px] text-ink">airgap mode</div>
          <div className="text-[12px] text-ink-muted">
            {airgap
              ? "ON — every model call runs on-device. nothing leaves this mac."
              : "off — claude is the brain, vault rules below still apply."}
          </div>
        </div>
        <button className="btn" onClick={toggleAirgap}>
          {airgap ? "turn off" : "turn on"}
        </button>
      </div>
      <div className="mt-4 border-t border-ink-faint pt-2">
        <div className="text-[13px] text-ink">vault lanes <span className="text-[12px] text-danger">{note}</span></div>
        <div className="text-[12px] text-ink-muted">
          anything matching these is only ever processed on-device, and its memory rows never enter a cloud prompt.
        </div>
        {editor("channels", "channels", "imessage, telegram, email, whatsapp")}
        {editor("contacts", "contacts", "names or handles, substring match")}
        {editor("addresses", "email addresses", "substring match")}
        {editor("domains", "agent domains", "health, finance, …")}
      </div>
    </div>
  );
}
