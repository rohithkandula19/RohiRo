import { PageHeader } from "@/components/editorial/PageHeader";
import { Divider } from "@/components/editorial/Divider";
import { MemoryWorkspace } from "@/components/memory/MemoryWorkspace";
import { LoopsCard } from "@/components/memory/LoopsCard";

export default function MemoryPage() {
  return (
    <div className="page">
      <PageHeader
        kicker="what i know"
        title="memory."
        subtitle="profile is the source of truth. contacts, decisions, lifetime archive, open loops."
      />
      <MemoryWorkspace />
      <Divider label="open loops" />
      <LoopsCard />
    </div>
  );
}
