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
        <div className="section-title"><h3>Integrations</h3><span className="text-[11.5px] text-ink-subtle">{ints.length} total</span></div>
        <div className="card overflow-hidden">
          {ints.map((i) => (
            <div key={i.name} className="flex items-center justify-between border-b border-line px-4 py-2.5 last:border-b-0">
              <div className="flex items-center gap-3">
                <span className="text-[13px] capitalize text-ink">{i.name.replace(/_/g, " ")}</span>
                {i.tier === 2 ? <span className="chip chip-warn">Tier 2</span> : null}
              </div>
              <div className="flex items-center gap-3">
                <span className="label">{i.connected ? "Connected" : "Off"}</span>
                <span className={"dot " + (i.connected ? "dot-ok" : "")} />
                <button className="btn btn-ghost px-2 py-0.5 text-[11.5px]">Test</button>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section>
        <div className="section-title"><h3>API keys</h3><span className="text-[11.5px] text-ink-subtle">stored in keychain</span></div>
        <div className="card overflow-hidden">
          {keys.map((k) => (
            <div key={k.name} className="flex items-center justify-between border-b border-line px-4 py-2.5 last:border-b-0">
              <span className="font-mono text-[12.5px] text-ink">{k.name}</span>
              <div className="flex items-center gap-3">
                <span className="font-mono text-[11.5px] text-ink-muted">{k.configured ? `…${k.last4}` : "not set"}</span>
                <button className="btn btn-ghost px-2 py-0.5 text-[11.5px]">Rotate</button>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section>
        <div className="section-title"><h3>Models</h3></div>
        {models ? (
          <div className="grid gap-3 md:grid-cols-3">
            <ModelCard label="Default" value={models.default} />
            <ModelCard label="Hard" value={models.hard} />
            <ModelCard label="Cheap" value={models.cheap} />
          </div>
        ) : null}
      </section>
    </div>
  );
}

function ModelCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="card p-4">
      <div className="label">{label}</div>
      <div className="mt-1 font-mono text-[12.5px] text-ink">{value}</div>
    </div>
  );
}
