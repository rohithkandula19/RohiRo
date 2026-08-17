import { PageHeader } from "@/components/editorial/PageHeader";
import { Divider } from "@/components/editorial/Divider";
import { SettingsView } from "@/components/settings/SettingsView";
import { PushCard } from "@/components/settings/PushCard";
import { LivenessCard } from "@/components/settings/LivenessCard";
import { LanesCard } from "@/components/settings/LanesCard";

export default function SettingsPage() {
  return (
    <div>
      <PageHeader
        kicker="under the hood"
        title="settings."
        subtitle="connections, models, keys (last 4 only), backup, voice."
      />
      <SettingsView />
      <Divider label="lanes" />
      <LanesCard />
      <Divider label="liveness" />
      <LivenessCard />
      <Divider label="notifications" />
      <PushCard />
    </div>
  );
}
