import { Hero } from "@/components/editorial/Hero";
import { Divider } from "@/components/editorial/Divider";
import { LiveTrace } from "@/components/trace/LiveTrace";
import { IntegrationsGrid } from "@/components/trace/IntegrationsGrid";

export default function OverviewPage() {
  return (
    <div>
      <div className="grid grid-cols-1 gap-10 md:grid-cols-2">
        <Hero />
        <LiveTrace />
      </div>

      <Divider label="connected · 14" />

      <IntegrationsGrid />

      <Divider label="today" />

      <div className="grid gap-3 md:grid-cols-3">
        <div className="card">
          <div className="kicker">pending</div>
          <p className="mt-2 text-[15px] leading-6 text-ink">
            3 drafts waiting on your ok. one for sarah, one slack reply,
            one calendar hold.
          </p>
        </div>
        <div className="card">
          <div className="kicker">done</div>
          <p className="mt-2 text-[15px] leading-6 text-ink">
            replied to 4 emails, archived 12, summarized this morning&apos;s
            standup, pushed a fix to rohflow.
          </p>
        </div>
        <div className="card">
          <div className="kicker">heads up</div>
          <p className="mt-2 text-[15px] leading-6 text-ink">
            photon round 2 tomorrow at 2pm. brief and prep are on the
            calendar page.
          </p>
        </div>
      </div>
    </div>
  );
}
