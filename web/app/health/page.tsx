import { PageHeader } from "@/components/editorial/PageHeader";
import { Divider } from "@/components/editorial/Divider";
import { HealthCards } from "@/components/health/HealthCards";

export default function HealthPage() {
  return (
    <div>
      <PageHeader
        kicker="apple health, strava"
        title="health."
        subtitle="steps, sleep, hr, weekly minutes. workouts pulled from strava."
      />
      <HealthCards />
      <Divider label="weekly trends" />
      <div className="card h-56 text-[13px] text-ink-muted">chart wires up in phase 5.</div>
    </div>
  );
}
