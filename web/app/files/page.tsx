import { PageHeader } from "@/components/editorial/PageHeader";
import { Divider } from "@/components/editorial/Divider";
import { FilesView } from "@/components/files/FilesView";

export default function FilesPage() {
  return (
    <div>
      <PageHeader
        kicker="drive, local, notion"
        title="files."
        subtitle="every file in one tree. hover for an ai summary."
      />
      <FilesView />
      <Divider label="tree" />
      <div className="card text-[13px] text-ink-muted">tree view wires up in phase 5.</div>
    </div>
  );
}
