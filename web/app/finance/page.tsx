import { PageHeader } from "@/components/editorial/PageHeader";
import { Divider } from "@/components/editorial/Divider";
import { FinanceView } from "@/components/finance/FinanceView";

export default function FinancePage() {
  return (
    <div>
      <PageHeader
        kicker="balances, expenses, subs"
        title="finance."
        subtitle="plaid is read-only here. ro never moves money. transfers always need your hands on the keys."
      />
      <FinanceView />
      <Divider label="invoices" />
      <div className="card text-[13px] text-ink-muted">no open invoices.</div>
    </div>
  );
}
