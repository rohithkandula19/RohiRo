import { PageHeader } from "@/components/editorial/PageHeader";
import { CrewView } from "@/components/bots/CrewView";

export default function BotsPage() {
  return (
    <div className="page">
      <PageHeader
        kicker="your crew"
        title="bots."
        subtitle="named ro's with charters. they delegate to each other, every handoff is logged, every outward write still stops at your yes."
      />
      <CrewView />
    </div>
  );
}
