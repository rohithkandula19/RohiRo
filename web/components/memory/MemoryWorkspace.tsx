"use client";

import { useEffect, useState } from "react";
import * as Tabs from "@radix-ui/react-tabs";

type Profile = { body: string; updated_at: string };
type Contact = { id: string; name: string; email?: string; role?: string; company?: string; notes?: string };
type Decision = { id: string; title: string; body: string; decided_at: string };

export function MemoryWorkspace() {
  const [profile, setProfile] = useState<Profile>({ body: "", updated_at: "" });
  const [dirty, setDirty] = useState(false);
  const [savedAt, setSavedAt] = useState<string>("");
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [search, setSearch] = useState("");
  const [hits, setHits] = useState<{ id: string; body: string }[]>([]);

  useEffect(() => {
    fetch("/api/memory/profile").then((r) => r.json()).then(setProfile).catch(() => null);
    fetch("/api/memory/contacts").then((r) => r.json()).then(setContacts).catch(() => null);
    fetch("/api/memory/decisions").then((r) => r.json()).then(setDecisions).catch(() => null);
  }, []);

  useEffect(() => {
    if (!dirty) return;
    const t = setTimeout(async () => {
      const r = await fetch("/api/memory/profile", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ body: profile.body }),
      });
      if (r.ok) {
        const updated = await r.json();
        setProfile(updated);
        setDirty(false);
        setSavedAt(new Date().toISOString());
      }
    }, 700);
    return () => clearTimeout(t);
  }, [dirty, profile.body]);

  async function runSearch(q: string) {
    setSearch(q);
    if (!q.trim()) { setHits([]); return; }
    const r = await fetch(`/api/memory/search?q=${encodeURIComponent(q)}&limit=8`);
    if (r.ok) setHits(await r.json());
  }

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <div className="card flex h-[540px] flex-col overflow-hidden">
        <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
          <div className="flex items-center gap-2">
            <span className="font-mono text-[12px] text-ink">profile.md</span>
          </div>
          <span className="label">{dirty ? "Saving…" : savedAt ? "Saved" : "In sync"}</span>
        </div>
        <textarea
          value={profile.body}
          onChange={(e) => { setProfile({ ...profile, body: e.target.value }); setDirty(true); }}
          className="h-full w-full resize-none bg-surface p-4 font-mono text-[12.5px] leading-6 text-ink outline-none"
          placeholder="# profile&#10;&#10;## who&#10;- name: ..."
        />
      </div>

      <div className="card flex h-[540px] flex-col overflow-hidden">
        <Tabs.Root defaultValue="contacts" className="flex h-full flex-col">
          <Tabs.List className="flex items-center gap-1 border-b border-line px-3 py-2">
            {["contacts", "decisions", "search"].map((k) => (
              <Tabs.Trigger
                key={k}
                value={k}
                className="rounded-[5px] px-2.5 py-1 text-[12.5px] capitalize text-ink-muted data-[state=active]:bg-accent-soft data-[state=active]:text-accent"
              >
                {k}
              </Tabs.Trigger>
            ))}
          </Tabs.List>

          <Tabs.Content value="contacts" className="flex-1 overflow-auto p-4">
            <table className="term-table">
              <thead>
                <tr><th>Name</th><th>Role</th><th>Company</th></tr>
              </thead>
              <tbody>
                {contacts.map((c) => (
                  <tr key={c.id}>
                    <td className="text-ink">{c.name}</td>
                    <td className="text-ink-muted">{c.role ?? ""}</td>
                    <td className="text-ink-muted">{c.company ?? ""}</td>
                  </tr>
                ))}
                {!contacts.length ? <tr><td colSpan={3} className="text-ink-subtle">No contacts.</td></tr> : null}
              </tbody>
            </table>
          </Tabs.Content>

          <Tabs.Content value="decisions" className="flex-1 overflow-auto p-4">
            <ul className="space-y-2">
              {decisions.map((d) => (
                <li key={d.id} className="rounded-[6px] border-l-2 border-accent bg-accent-soft p-3">
                  <div className="text-[10.5px] uppercase tracking-wider text-accent">{new Date(d.decided_at).toLocaleDateString()}</div>
                  <div className="mt-1 text-[13px] font-medium text-ink">{d.title}</div>
                  <div className="text-[12px] text-ink-muted">{d.body}</div>
                </li>
              ))}
              {!decisions.length ? <li className="text-[13px] text-ink-subtle">No decisions logged.</li> : null}
            </ul>
          </Tabs.Content>

          <Tabs.Content value="search" className="flex-1 overflow-auto p-4">
            <input
              className="input"
              placeholder="Search past conversations and notes"
              value={search}
              onChange={(e) => runSearch(e.target.value)}
            />
            <ul className="mt-3 space-y-2">
              {hits.map((h) => (
                <li key={h.id} className="rounded-[6px] border border-line bg-surface-hover p-3 text-[12px] text-ink-muted">
                  {h.body.slice(0, 280)}
                </li>
              ))}
            </ul>
          </Tabs.Content>
        </Tabs.Root>
      </div>
    </div>
  );
}
