"use client";

import { useEffect, useState } from "react";

type Integration = { name: string; connected: boolean; tier: number; last_sync: string | null };
type Key = { name: string; configured: boolean; last4: string };
type Models = { default: string; hard: string; cheap: string };

export function SettingsView() {
  const [ints, setInts] = useState<Integration[]>([]);
  const [keys, setKeys] = useState<Key[]>([]);
  const [models, setModels] = useState<Models | null>(null);

  useEffect(() => {
    fetch("/api/settings/integrations").then((r) => r.json()).then(setInts).catch(() => null);
    fetch("/api/settings/keys").then((r) => r.json()).then(setKeys).catch(() => null);
    fetch("/api/settings/models").then((r) => r.json()).then(setModels).catch(() => null);
  }, []);

  return (
    <div className="space-y-8">
      <section>
        <div className="kicker mb-3">integrations</div>
        <div className="overflow-hidden rounded-card border border-hair border-line">
          {ints.map((i) => (
            <div key={i.name} className="flex items-center justify-between border-b border-hair border-line-subtle bg-surface p-3 last:border-b-0">
              <div className="flex items-center gap-3">
                <span className="font-mono text-[12.5px] text-ink">{i.name}</span>
                {i.tier === 2 ? <span className="chip">tier 2</span> : null}
              </div>
              <div className="flex items-center gap-3">
                <span className="kicker">{i.connected ? "connected" : "off"}</span>
                <span className={`h-1.5 w-1.5 rounded-full ${i.connected ? "bg-success" : "bg-ink-subtle"}`} />
                <button className="btn-secondary px-3 py-1 text-[11px]">test</button>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section>
        <div className="kicker mb-3">api keys</div>
        <div className="overflow-hidden rounded-card border border-hair border-line">
          {keys.map((k) => (
            <div key={k.name} className="flex items-center justify-between border-b border-hair border-line-subtle bg-surface p-3 last:border-b-0">
              <span className="font-mono text-[12.5px] text-ink">{k.name}</span>
              <div className="flex items-center gap-3">
                <span className="font-mono text-[11px] text-ink-muted">
                  {k.configured ? `…${k.last4}` : "not set"}
                </span>
                <button className="btn-secondary px-3 py-1 text-[11px]">rotate</button>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section>
        <div className="kicker mb-3">models</div>
        {models ? (
          <div className="card grid grid-cols-3 gap-4 text-[13px]">
            <div><div className="kicker">default</div><div className="mt-1 font-mono">{models.default}</div></div>
            <div><div className="kicker">hard</div><div className="mt-1 font-mono">{models.hard}</div></div>
            <div><div className="kicker">cheap</div><div className="mt-1 font-mono">{models.cheap}</div></div>
          </div>
        ) : null}
      </section>
    </div>
  );
}
