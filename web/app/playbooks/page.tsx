import { PageHeader } from "@/components/editorial/PageHeader";
import { PlaybooksView } from "@/components/playbooks/PlaybooksView";
import { TriggersCard } from "@/components/playbooks/TriggersCard";
import { RoutinesCard } from "@/components/playbooks/RoutinesCard";

export default function PlaybooksPage() {
  return (
    <div>
      <PageHeader
        kicker="teach ro"
        title="playbooks."
        subtitle="describe a task once. run it on demand, on a schedule, or when a matching event arrives."
      />
      <PlaybooksView />
      <TriggersCard />
      <RoutinesCard />
    </div>
  );
}
