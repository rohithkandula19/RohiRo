import { PageHeader } from "@/components/editorial/PageHeader";
import { Divider } from "@/components/editorial/Divider";
import { WeekView } from "@/components/calendar/WeekView";

export default function CalendarPage() {
  return (
    <div>
      <PageHeader
        kicker="time"
        title="calendar."
        subtitle="this week, with prep briefs in line."
      />
      <WeekView />
      <Divider label="negotiations" />
      <div className="card max-w-xl">
        <div className="kicker">photon labs round 2</div>
        <div className="mt-2 text-[14px] text-ink">
          waiting on sarah&apos;s reply to the proposed slots. last action: tuesday 2 to 3:30 et.
        </div>
      </div>
    </div>
  );
}
