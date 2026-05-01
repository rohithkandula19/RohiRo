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
        <div key={r.name} className="card">
          <div className="flex items-center justify-between">
            <div className="font-mono text-[13px] text-ink">{r.name}</div>
            <span className={`h-2 w-2 rounded-full ${ciColor(r.ci)}`} />
          </div>
          <div className="mt-2 line-clamp-2 text-[13px] text-ink-muted">{r.last_commit}</div>
          <div className="mt-3 flex items-center gap-2">
            <span className="chip">deploy: {r.deploy}</span>
            <span className="chip">prs: {r.open_prs}</span>
          </div>
          <div className="mt-3 flex gap-2">
            <button className="btn-secondary px-3 py-1.5 text-[12px]">summarize commits</button>
            <button className="btn-secondary px-3 py-1.5 text-[12px]">open in claude code</button>
          </div>
        </div>
      ))}
    </div>
  );
}

function ciColor(v: string) {
  if (v === "green") return "bg-success";
  if (v === "yellow") return "bg-warning";
  if (v === "red") return "bg-danger";
  return "bg-ink-subtle";
}
