import { PageHeader } from "@/components/editorial/PageHeader";
import { Divider } from "@/components/editorial/Divider";
import { MemoryWorkspace } from "@/components/memory/MemoryWorkspace";

export default function MemoryPage() {
  return (
    <div>
      <PageHeader
        kicker="what i know"
        title="memory."
        subtitle="profile is the source of truth. contacts, decisions, conversation history, everything searchable."
      />
      <MemoryWorkspace />
      <Divider label="search history" />
      <div className="card text-[13px] text-ink-muted">use the search box above to query past conversations.</div>
    </div>
  );
}
