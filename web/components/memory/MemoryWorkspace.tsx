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
    if (!q.trim()) {
      setHits([]);
      return;
    }
    const r = await fetch(`/api/memory/search?q=${encodeURIComponent(q)}&limit=8`);
    if (r.ok) setHits(await r.json());
  }

  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
      <div className="card flex h-[520px] flex-col">
        <div className="flex items-center justify-between">
          <div className="kicker">profile.md</div>
          <div className="kicker">
            {dirty ? "saving" : savedAt ? "saved" : "in sync"}
          </div>
        </div>
        <textarea
          value={profile.body}
          onChange={(e) => {
            setProfile({ ...profile, body: e.target.value });
            setDirty(true);
          }}
          className="mt-3 h-full w-full resize-none rounded-button bg-bg p-3 font-mono text-[12.5px] leading-6 text-ink outline-none"
          placeholder="# profile&#10;&#10;## who&#10;- name: ..."
        />
      </div>

      <div className="card h-[520px] overflow-hidden">
        <Tabs.Root defaultValue="contacts" className="flex h-full flex-col">
          <Tabs.List className="flex gap-3 border-b border-hair border-line-subtle pb-2">
            {["contacts", "decisions", "search"].map((k) => (
              <Tabs.Trigger
                key={k}
                value={k}
                className="kicker px-1 py-1 data-[state=active]:text-accent"
              >
                {k}
              </Tabs.Trigger>
            ))}
          </Tabs.List>

          <Tabs.Content value="contacts" className="mt-3 flex-1 overflow-auto">
            <table className="w-full text-[13px]">
              <thead className="kicker text-ink-subtle">
                <tr>
                  <th className="py-1 text-left">name</th>
                  <th className="py-1 text-left">role</th>
                  <th className="py-1 text-left">company</th>
                </tr>
              </thead>
              <tbody>
                {contacts.map((c) => (
                  <tr key={c.id} className="border-t border-hair border-line-subtle">
                    <td className="py-2">{c.name}</td>
                    <td className="py-2 text-ink-muted">{c.role ?? ""}</td>
                    <td className="py-2 text-ink-muted">{c.company ?? ""}</td>
                  </tr>
                ))}
                {!contacts.length ? (
                  <tr><td colSpan={3} className="py-3 text-ink-subtle">no contacts yet.</td></tr>
                ) : null}
              </tbody>
            </table>
          </Tabs.Content>

          <Tabs.Content value="decisions" className="mt-3 flex-1 overflow-auto">
            <ul className="space-y-3">
              {decisions.map((d) => (
                <li key={d.id} className="rounded-button border border-hair border-line-subtle p-3">
                  <div className="kicker">{new Date(d.decided_at).toLocaleDateString()}</div>
                  <div className="mt-1 text-[13px] text-ink">{d.title}</div>
                  <div className="text-[12.5px] text-ink-muted">{d.body}</div>
                </li>
              ))}
              {!decisions.length ? (
                <li className="text-[13px] text-ink-subtle">no decisions logged yet.</li>
              ) : null}
            </ul>
          </Tabs.Content>

          <Tabs.Content value="search" className="mt-3 flex-1 overflow-auto">
            <input
              className="input w-full"
              placeholder="search past conversations and notes"
              value={search}
              onChange={(e) => runSearch(e.target.value)}
            />
            <ul className="mt-3 space-y-2">
              {hits.map((h) => (
                <li key={h.id} className="rounded-button border border-hair border-line-subtle p-3 text-[12.5px] text-ink-muted">
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
