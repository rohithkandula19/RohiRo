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
      <div className="flex flex-wrap gap-1.5">
        {SOURCES.map((s) => (
          <button
            key={s}
            onClick={() => setSource(s)}
            className={
              "rounded-[5px] border px-2.5 py-1 text-[12px] capitalize " +
              (source === s
                ? "border-accent/30 bg-accent-soft text-accent"
                : "border-line bg-surface text-ink-muted hover:bg-surface-hover")
            }
          >
            {s}
          </button>
        ))}
      </div>

      <div className="card mt-4 overflow-hidden">
        {files.map((f) => (
          <div key={f.id} className="flex items-center justify-between border-b border-line px-4 py-2.5 last:border-b-0 hover:bg-surface-hover">
            <div className="text-[13px] text-ink">{f.name}</div>
            <div className="flex items-center gap-3">
              <span className="chip capitalize">{f.source}</span>
              <span className="text-[11.5px] text-ink-subtle">{f.modified}</span>
            </div>
          </div>
        ))}
        {!files.length ? <div className="p-4 text-[13px] text-ink-subtle">No recent files.</div> : null}
      </div>
    </div>
  );
}
