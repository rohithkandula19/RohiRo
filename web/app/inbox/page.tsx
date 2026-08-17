import { PageHeader } from "@/components/editorial/PageHeader";
import { InboxView } from "@/components/inbox/InboxView";
import { ApprovalsList } from "@/components/inbox/ApprovalsList";
import { Divider } from "@/components/editorial/Divider";

export default function InboxPage() {
  return (
    <div>
      <PageHeader
        kicker="inbox"
        title="Inbox"
        subtitle="Every channel in one place. Drafts wait for your ok before they go out."
      />

      <Divider label="Awaiting approval" />
      <ApprovalsList />

      <Divider label="Messages" />
      <InboxView />
    </div>
  );
}
