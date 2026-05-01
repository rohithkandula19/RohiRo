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
        <div key={p.id} className="card">
          <div className="kicker">{p.status}</div>
          <h3 className="mt-2 font-serif text-[18px] leading-snug">{p.title}</h3>
          <div className="mt-1 text-[12px] text-ink-muted">{p.authors}</div>
        </div>
      ))}
    </div>
  );
}
