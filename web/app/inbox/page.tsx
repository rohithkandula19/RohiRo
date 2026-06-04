import { PageHeader } from "@/components/editorial/PageHeader";
import { InboxView } from "@/components/inbox/InboxView";
import { Divider } from "@/components/editorial/Divider";

export default function InboxPage() {
  return (
    <div>
      <PageHeader
        kicker="inbox"
        title="Inbox"
        subtitle="Every channel in one place. Drafts wait for your ok before they go out."
      />

      <Divider label="Awaiting approval" right={<span>1 draft</span>} />
      <div className="card overflow-hidden">
        <div className="flex items-center justify-between border-b border-line bg-warning/[0.04] px-4 py-2.5">
          <div className="flex items-center gap-2 text-[12px]">
            <span className="chip chip-warn">Approval</span>
            <span className="text-ink-muted">Send email to Sarah Lin</span>
          </div>
          <span className="text-[11px] text-ink-subtle">via Gmail · drafted 2m ago</span>
        </div>
        <div className="p-4">
          <div className="rounded-[6px] border-l-2 border-warning bg-surface-hover px-3 py-2.5 text-[13px] leading-6 text-ink">
            Tuesday afternoon works. I&apos;ll block 2 to 3:30 ET and send a calendar
            hold. Anything specific you want me to dig into beforehand?
          </div>
          <div className="mt-3 flex gap-2">
            <button className="btn btn-primary">Approve & send</button>
            <button className="btn">Edit</button>
            <button className="btn btn-danger">Reject</button>
          </div>
        </div>
      </div>

      <Divider label="Messages" />
      <InboxView />
    </div>
  );
}
