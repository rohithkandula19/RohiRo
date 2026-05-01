"use client";

import { useEffect, useState } from "react";

type Integration = { name: string; connected: boolean; tier: number; last_sync: string | null };

async function fetcher(path: string) {
  const r = await fetch(path);
  if (!r.ok) throw new Error("fetch failed");
  return r.json();
}

export function IntegrationsGrid() {
  const [items, setItems] = useState<Integration[]>([]);
  useEffect(() => {
    fetcher("/api/settings/integrations")
      .then(setItems)
      .catch(() => setItems([]));
  }, []);

  if (!items.length) {
    return (
      <div className="grid grid-cols-2 gap-2 md:grid-cols-7">
        {Array.from({ length: 14 }).map((_, i) => (
          <div key={i} className="h-[68px] rounded-card border border-hair border-line-subtle bg-surface" />
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-2 md:grid-cols-7">
      {items.map((i) => (
        <div
          key={i.name}
          className="rounded-card border border-hair border-line-subtle bg-surface px-3 py-3"
        >
          <div className="flex items-center justify-between">
            <span className="text-[12.5px] text-ink">{labelize(i.name)}</span>
            <span
              className={`h-1.5 w-1.5 rounded-full ${i.connected ? "bg-success" : "bg-ink-subtle"}`}
            />
          </div>
          <div className="kicker mt-2">
            {i.tier === 2 ? "tier 2" : i.connected ? "ready" : "off"}
          </div>
        </div>
      ))}
    </div>
  );
}

function labelize(name: string) {
  return name.replace(/_/g, " ");
}
