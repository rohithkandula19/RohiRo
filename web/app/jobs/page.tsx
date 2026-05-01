import { PageHeader } from "@/components/editorial/PageHeader";
import { Divider } from "@/components/editorial/Divider";
import { JobsKanban } from "@/components/jobs/JobsKanban";

export default function JobsPage() {
  return (
    <div>
      <PageHeader
        kicker="opportunities"
        title="jobs."
        subtitle="every application, every recruiter thread, every prep card. powered by ro job bot."
      />
      <JobsKanban />
      <Divider label="recruiter threads" />
      <div className="card">
        <div className="text-[13px] text-ink-muted">live thread view wires up in phase 5.</div>
      </div>
    </div>
  );
}
