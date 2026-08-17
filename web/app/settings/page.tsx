import { PageHeader } from "@/components/editorial/PageHeader";
import { Divider } from "@/components/editorial/Divider";
import { SettingsView } from "@/components/settings/SettingsView";
import { PushCard } from "@/components/settings/PushCard";
import { LivenessCard } from "@/components/settings/LivenessCard";

export default function SettingsPage() {
  return (
    <div>
      <PageHeader
        kicker="under the hood"
        title="settings."
        subtitle="connections, models, keys (last 4 only), backup, voice."
      />
      <SettingsView />
      <Divider label="liveness" />
      <LivenessCard />
      <Divider label="notifications" />
      <PushCard />
    </div>
  );
}
