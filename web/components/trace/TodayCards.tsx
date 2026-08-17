"use client";

import { useEffect, useState } from "react";

type Counts = { pending: number; executed: number; upcoming: number };

export function TodayCards() {
  const [counts, setCounts] = useState<Counts | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [approvals, sent, schedules] = await Promise.all([
          fetch("/api/approvals").then((r) => r.json()).catch(() => []),
          fetch("/api/audit").then((r) => r.json()).catch(() => []),
          fetch("/api/schedules").then((r) => r.json()).catch(() => []),
        ]);
        const today = new Date().toDateString();
        setCounts({
          pending: Array.isArray(approvals) ? approvals.length : 0,
          executed: Array.isArray(sent)
            ? sent.filter((e: { created_at: string }) => new Date(e.created_at).toDateString() === today).length
            : 0,
          upcoming: Array.isArray(schedules)
            ? schedules.filter((s: { enabled: boolean }) => s.enabled).length
            : 0,
        });
      } catch {
        setCounts(null);
      }
    }
    load();
  }, []);

  const c = counts;
  return (
    <>
      <div className="mt-8 mb-3 flex items-center gap-3">
        <span className="text-[10.5px] font-medium uppercase tracking-wider text-ink-subtle">Today</span>
        <span className="h-px flex-1 bg-line" />
        <span className="text-[11px] text-ink-subtle">
          {c ? `${c.pending} pending · ${c.executed} sent · ${c.upcoming} routines armed` : "loading…"}
        </span>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <Card
          tag="Pending" tagClass="chip-warn" link="/inbox" linkLabel="Review"
          body={
            c === null ? "checking…"
            : c.pending === 0 ? "Nothing waiting on your approval."
            : `${c.pending} action${c.pending === 1 ? "" : "s"} waiting on your yes.`
          }
        />
        <Card
          tag="Sent" tagClass="chip-ok" link="/audit" linkLabel="See receipts"
          body={
            c === null ? "checking…"
            : c.executed === 0 ? "Nothing sent today. Every departure gets a receipt on the audit page."
            : `${c.executed} outward action${c.executed === 1 ? "" : "s"} today, each with a ledger receipt.`
          }
        />
        <Card
          tag="Routines" tagClass="chip-accent" link="/playbooks" linkLabel="Manage"
          body={
            c === null ? "checking…"
            : c.upcoming === 0 ? "No routines scheduled yet. Teach one on the playbooks page."
            : `${c.upcoming} routine${c.upcoming === 1 ? "" : "s"} armed and on schedule.`
          }
        />
      </div>
    </>
  );
}

function Card({ tag, tagClass, body, link, linkLabel }: {
  tag: string; tagClass: string; body: string; link: string; linkLabel: string;
}) {
  return (
    <div className="card p-4">
      <span className={"chip " + tagClass}>{tag}</span>
      <p className="mt-3 text-[13.5px] leading-6 text-ink">{body}</p>
      <a href={link} className="mt-3 inline-block text-[12px] font-medium text-accent hover:text-accent-hover">
        {linkLabel} →
      </a>
    </div>
  );
}
