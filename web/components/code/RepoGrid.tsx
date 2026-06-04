"use client";

import { useEffect, useState } from "react";

type Repo = {
  name: string;
  last_commit: string;
  ci: "green" | "yellow" | "red" | string;
  deploy: string;
  open_prs: number;
};

export function RepoGrid() {
  const [repos, setRepos] = useState<Repo[]>([]);
  useEffect(() => {
    fetch("/api/code/repos")
      .then((r) => r.json())
      .then(setRepos)
      .catch(() => setRepos([]));
  }, []);

  return (
    <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
      {repos.map((r) => (
        <div key={r.name} className="card p-4">
          <div className="flex items-center justify-between">
            <div className="font-mono text-[12.5px] font-medium text-ink">{r.name}</div>
            <span className={"chip " + ciChip(r.ci)}>{r.ci}</span>
          </div>
          <div className="meta mt-1.5 line-clamp-2">{r.last_commit}</div>
          <div className="mt-3 flex items-center gap-1.5">
            <span className="chip">deploy: {r.deploy}</span>
            <span className="chip">{r.open_prs} PRs</span>
          </div>
          <div className="mt-3 flex gap-1.5">
            <button className="btn btn-ghost px-2 py-1 text-[11.5px]">Summarize</button>
            <button className="btn btn-ghost px-2 py-1 text-[11.5px]">Open in Claude Code</button>
          </div>
        </div>
      ))}
      {!repos.length ? <div className="meta">No repos connected yet.</div> : null}
    </div>
  );
}

function ciChip(v: string) {
  if (v === "green") return "chip-ok";
  if (v === "yellow") return "chip-warn";
  if (v === "red") return "chip-bad";
  return "";
}
