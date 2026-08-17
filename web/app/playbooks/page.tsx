import { PageHeader } from "@/components/editorial/PageHeader";
import { PlaybooksView } from "@/components/playbooks/PlaybooksView";

export default function PlaybooksPage() {
  return (
    <div>
      <PageHeader
        kicker="teach ro"
        title="playbooks."
        subtitle="describe a task once. run it on demand or on a schedule. steps chain, approvals still gate."
      />
      <PlaybooksView />
    </div>
  );
}
