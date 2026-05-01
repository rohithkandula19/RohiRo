import { PageHeader } from "@/components/editorial/PageHeader";
import { Divider } from "@/components/editorial/Divider";
import { ReadingList } from "@/components/research/ReadingList";

export default function ResearchPage() {
  return (
    <div>
      <PageHeader
        kicker="papers, threads, threads on threads"
        title="research."
        subtitle="reading list, arxiv watch, and full citation history. ask the research agent at the bottom."
      />
      <ReadingList />
      <Divider label="arxiv watchlist" />
      <div className="card text-[13px] text-ink-muted">arxiv tracker plugs in during phase 5.</div>
      <Divider label="ask the research agent" />
      <div className="card max-w-2xl">
        <input className="input w-full" placeholder="what do you want to know?" />
      </div>
    </div>
  );
}
