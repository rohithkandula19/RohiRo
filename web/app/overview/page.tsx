import { Hero } from "@/components/editorial/Hero";
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

      <Divider label="Today" right={<span>3 pending · 18 done · 1 upcoming</span>} />

      <div className="grid gap-3 md:grid-cols-3">
        <SummaryCard
          tag="Pending"
          tagClass="chip-warn"
          body="3 drafts waiting on your ok. One for Sarah, one Slack reply, one calendar hold."
          link="/inbox"
          linkLabel="Review"
        />
        <SummaryCard
          tag="Done"
          tagClass="chip-ok"
          body="Replied to 4 emails, archived 12, summarized standup, pushed a fix to rohflow."
          link="/code"
          linkLabel="View activity"
        />
        <SummaryCard
          tag="Upcoming"
          tagClass="chip-accent"
          body="Photon round 2 tomorrow at 2pm ET. Brief and prep are on the calendar page."
          link="/calendar"
          linkLabel="Open calendar"
        />
      </div>

      <Divider label="Connected services" right={<span>14 integrations</span>} />
      <IntegrationsGrid />
    </div>
  );
}

function SummaryCard({
  tag, tagClass, body, link, linkLabel,
}: { tag: string; tagClass: string; body: string; link: string; linkLabel: string }) {
  return (
    <div className="card p-4">
      <span className={"chip " + tagClass}>{tag}</span>
      <p className="mt-3 text-[13.5px] leading-6 text-ink">{body}</p>
      <a href={link} className="mt-3 inline-block text-[12px] font-medium text-accent hover:text-accent-hover">
        {linkLabel} →
      </a>
    </div>
  );
}
