import { PageHeader } from "@/components/editorial/PageHeader";
import { Divider } from "@/components/editorial/Divider";
import { SettingsView } from "@/components/settings/SettingsView";

export default function SettingsPage() {
  return (
    <div>
      <PageHeader
        kicker="under the hood"
        title="settings."
        subtitle="connections, models, keys (last 4 only), backup, voice."
      />
      <SettingsView />
      <Divider label="approval rules" />
      <div className="card max-w-2xl text-[13px] text-ink-muted">
        per-domain approval rules wire up in phase 3.
      </div>
    </div>
  );
}
