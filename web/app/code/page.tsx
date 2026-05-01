import { PageHeader } from "@/components/editorial/PageHeader";
import { Divider } from "@/components/editorial/Divider";
import { RepoGrid } from "@/components/code/RepoGrid";

export default function CodePage() {
  return (
    <div>
      <PageHeader
        kicker="repos"
        title="code."
        subtitle="active repos, recent commits, ci status, deploys, prs. handoff to claude code in one click."
      />
      <RepoGrid />
      <Divider label="cross-repo issues" />
      <div className="card">
        <div className="text-[13px] text-ink-muted">issues feed plugs in during phase 5.</div>
      </div>
    </div>
  );
}
