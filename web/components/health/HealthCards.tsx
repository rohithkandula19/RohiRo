"use client";

import { useEffect, useState } from "react";

type Today = {
  steps: number;
  sleep_hours: number;
  resting_hr: number;
  weekly_active_minutes: number;
  weekly_goal: number;
};

export function HealthCards() {
  const [today, setToday] = useState<Today | null>(null);
  useEffect(() => {
    fetch("/api/health/today")
      .then((r) => r.json())
      .then(setToday)
      .catch(() => setToday(null));
  }, []);

  if (!today) return <div className="meta">No data yet.</div>;

  const pct = Math.min(100, Math.round((today.weekly_active_minutes / today.weekly_goal) * 100));

  return (
    <div className="grid gap-3 md:grid-cols-4">
      <Card label="Steps today" value={today.steps.toLocaleString()} />
      <Card label="Sleep last night" value={`${today.sleep_hours.toFixed(1)}h`} />
      <Card label="Resting HR" value={`${today.resting_hr} bpm`} />
      <div className="card p-4">
        <div className="label">Weekly active</div>
        <div className="mt-1 text-[22px] font-semibold tracking-tight text-ink">{today.weekly_active_minutes} min</div>
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-surface-hover">
          <div className="h-full rounded-full bg-accent" style={{ width: `${pct}%` }} />
        </div>
        <div className="mt-1.5 text-[11px] text-ink-subtle">{pct}% of {today.weekly_goal} min goal</div>
      </div>
    </div>
  );
}

function Card({ label, value }: { label: string; value: string }) {
  return (
    <div className="card p-4">
      <div className="label">{label}</div>
      <div className="mt-1 text-[22px] font-semibold tracking-tight text-ink">{value}</div>
    </div>
  );
}
