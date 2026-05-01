"use client";

import { useEffect, useState } from "react";

type File = { id: string; name: string; source: string; modified: string };
const SOURCES = ["all", "drive", "local", "notion"];

export function FilesView() {
  const [source, setSource] = useState("all");
  const [files, setFiles] = useState<File[]>([]);

  useEffect(() => {
    const params = source === "all" ? "" : `?source=${source}`;
    fetch(`/api/files/recent${params}`)
      .then((r) => r.json())
      .then(setFiles)
      .catch(() => setFiles([]));
  }, [source]);

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {SOURCES.map((s) => (
          <button
            key={s}
            onClick={() => setSource(s)}
            className={
              "rounded-button border border-hair px-3 py-1.5 text-[12px] " +
              (source === s ? "border-accent bg-accent-soft text-accent" : "border-line text-ink-muted")
            }
          >
            {s}
          </button>
        ))}
      </div>

      <div className="mt-6 overflow-hidden rounded-card border border-hair border-line">
        {files.map((f) => (
          <div key={f.id} className="flex items-center justify-between border-b border-hair border-line-subtle bg-surface p-3 last:border-b-0">
            <div className="font-mono text-[12.5px] text-ink">{f.name}</div>
            <div className="flex items-center gap-3">
              <span className="chip">{f.source}</span>
              <span className="kicker">{f.modified}</span>
            </div>
          </div>
        ))}
        {!files.length ? <div className="p-4 text-[13px] text-ink-subtle">no recent files.</div> : null}
      </div>
    </div>
  );
}
