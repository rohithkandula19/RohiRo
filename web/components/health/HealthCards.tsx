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

  if (!today) return <div className="text-[13px] text-ink-subtle">no data yet.</div>;

  const pct = Math.min(100, Math.round((today.weekly_active_minutes / today.weekly_goal) * 100));

  return (
    <div className="grid gap-3 md:grid-cols-4">
      <Card label="steps today" value={today.steps.toLocaleString()} />
      <Card label="sleep last night" value={`${today.sleep_hours.toFixed(1)} h`} />
      <Card label="resting hr" value={`${today.resting_hr} bpm`} />
      <div className="card">
        <div className="kicker">weekly active</div>
        <div className="mt-2 font-serif text-[24px]">{today.weekly_active_minutes} min</div>
        <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-accent-soft">
          <div className="h-full bg-accent" style={{ width: `${pct}%` }} />
        </div>
        <div className="mt-2 font-mono text-[10.5px] text-ink-subtle">{pct}% of {today.weekly_goal}</div>
      </div>
    </div>
  );
}

function Card({ label, value }: { label: string; value: string }) {
  return (
    <div className="card">
      <div className="kicker">{label}</div>
      <div className="mt-2 font-serif text-[24px]">{value}</div>
    </div>
  );
}
