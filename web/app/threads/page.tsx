import { PageHeader } from "@/components/editorial/PageHeader";
import { ThreadsView } from "@/components/threads/ThreadsView";

export default function ThreadsPage() {
  return (
    <div>
      <PageHeader
        kicker="the room where it happens"
        title="threads."
        subtitle="every conversation across every channel, with the actions each turn opened, inline."
      />
      <ThreadsView />
    </div>
  );
}
