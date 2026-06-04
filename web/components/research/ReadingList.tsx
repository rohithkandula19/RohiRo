"use client";

import { useEffect, useState } from "react";

type Paper = { id: string; title: string; authors: string; status: string };

export function ReadingList() {
  const [papers, setPapers] = useState<Paper[]>([]);
  useEffect(() => {
    fetch("/api/research/reading-list")
      .then((r) => r.json())
      .then(setPapers)
      .catch(() => setPapers([]));
  }, []);

  return (
    <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
      {papers.map((p) => (
        <div key={p.id} className="card p-4 card-hover">
          <span className="chip capitalize">{p.status}</span>
          <h3 className="mt-3 text-[14.5px] font-semibold leading-snug text-ink">{p.title}</h3>
          <div className="meta mt-1">{p.authors}</div>
        </div>
      ))}
      {!papers.length ? <div className="meta">No papers in your reading list.</div> : null}
    </div>
  );
}
