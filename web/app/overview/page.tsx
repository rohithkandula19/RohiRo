import { Hero } from "@/components/editorial/Hero";
import { TodayCards } from "@/components/trace/TodayCards";
import { Divider } from "@/components/editorial/Divider";
import { LiveTrace } from "@/components/trace/LiveTrace";
import { IntegrationsGrid } from "@/components/trace/IntegrationsGrid";
import { PageHeader } from "@/components/editorial/PageHeader";

export default function OverviewPage() {
  return (
    <div>
      <PageHeader
        kicker="overview"
        title="Overview"
        subtitle="Everything ro did today, what's pending, and what's coming up."
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        <div className="lg:col-span-3"><Hero /></div>
        <div className="lg:col-span-2"><LiveTrace /></div>
      </div>

      <TodayCards />

      <Divider label="Connected services" right={<span>14 integrations</span>} />
      <IntegrationsGrid />
    </div>
  );
}

