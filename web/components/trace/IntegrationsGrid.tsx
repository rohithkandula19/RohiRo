"use client";

import { useEffect, useState } from "react";

type Integration = { name: string; connected: boolean; tier: number; last_sync: string | null };

export function IntegrationsGrid() {
  const [items, setItems] = useState<Integration[]>([]);
  useEffect(() => {
    fetch("/api/settings/integrations")
      .then((r) => r.json())
      .then(setItems)
      .catch(() => setItems([]));
  }, []);

  if (!items.length) {
    return (
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4 lg:grid-cols-7">
        {Array.from({ length: 14 }).map((_, i) => (
          <div key={i} className="card h-[64px]" />
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-2 md:grid-cols-4 lg:grid-cols-7">
      {items.map((i) => (
        <div key={i.name} className="card card-hover px-3 py-2.5">
          <div className="flex items-center justify-between">
            <span className="text-[12.5px] font-medium capitalize text-ink">{i.name.replace(/_/g, " ")}</span>
            <span className={`dot ${i.connected ? "dot-ok" : ""}`} />
          </div>
          <div className="label mt-1.5">
            {i.tier === 2 ? "Tier 2" : i.connected ? "Connected" : "Not connected"}
          </div>
        </div>
      ))}
    </div>
  );
}
