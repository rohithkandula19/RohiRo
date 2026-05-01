import { PageHeader } from "@/components/editorial/PageHeader";
import { InboxView } from "@/components/inbox/InboxView";
import { Divider } from "@/components/editorial/Divider";

export default function InboxPage() {
  return (
    <div>
      <PageHeader
        kicker="unified messaging"
        title="inbox."
        subtitle="every channel in one place. drafts wait for your ok before they go out."
      />
      <Divider label="pending · 1" />
      <div className="mb-8 rounded-card border border-hair border-warning/40 bg-warning/5 p-4">
        <div className="kicker text-warning">approval needed · send email</div>
        <div className="mt-2 text-[14px] text-ink">
          reply to sarah lin at photon labs about round 2.
        </div>
        <div className="mt-3 flex gap-2">
          <button className="btn-primary">approve</button>
          <button className="btn-secondary">edit</button>
          <button className="btn-secondary">reject</button>
        </div>
      </div>
      <Divider label="messages" />
      <InboxView />
    </div>
  );
}
