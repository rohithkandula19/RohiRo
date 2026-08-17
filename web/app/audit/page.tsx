import { PageHeader } from "@/components/editorial/PageHeader";
import { AuditView } from "@/components/audit/AuditView";

export default function AuditPage() {
  return (
    <div>
      <PageHeader
        kicker="receipts"
        title="audit."
        subtitle="every outward byte, hash-chained. verify the chain yourself — it's a query, not a promise."
      />
      <AuditView />
    </div>
  );
}
