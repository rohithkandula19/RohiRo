"use client";

import { useEffect, useState } from "react";

type Event = {
  id: string;
  title: string;
  start: string;
  end: string;
  attendees: string[];
  prep: string;
};

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function WeekView() {
  const [events, setEvents] = useState<Event[]>([]);
  const [open, setOpen] = useState<Event | null>(null);

  useEffect(() => {
    fetch("/api/calendar/week")
      .then((r) => r.json())
      .then(setEvents)
      .catch(() => setEvents([]));
  }, []);

  return (
    <div>
      <div className="grid grid-cols-7 gap-2">
        {DAYS.map((d, i) => (
          <div key={d} className="card min-h-[180px] p-3">
            <div className="flex items-baseline justify-between">
              <div className="text-[12px] font-semibold text-ink">{d}</div>
              <div className="text-[10.5px] text-ink-subtle">{i + 1}</div>
            </div>
            <div className="mt-2 space-y-1.5">
              {events
                .filter((e) => new Date(e.start).getDay() === ((i + 1) % 7))
                .map((e) => (
                  <button
                    key={e.id}
                    onClick={() => setOpen(e)}
                    className="block w-full rounded-[5px] border-l-2 border-accent bg-accent-soft p-2 text-left hover:bg-accent/10"
                  >
                    <div className="text-[10.5px] text-accent">
                      {new Date(e.start).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}
                    </div>
                    <div className="mt-0.5 text-[12px] font-medium text-ink">{e.title}</div>
                  </button>
                ))}
            </div>
          </div>
        ))}
      </div>

      {open ? (
        <div className="card mt-5 max-w-2xl p-5">
          <div className="flex items-center justify-between">
            <span className="chip chip-accent">Prep brief</span>
            <button onClick={() => setOpen(null)} className="btn btn-ghost px-2 py-0.5 text-[12px]">Close</button>
          </div>
          <h3 className="mt-3 text-[18px] font-semibold text-ink">{open.title}</h3>
          <div className="meta mt-1">{open.attendees.join(" · ")}</div>
          <p className="mt-3 text-[13px] leading-6 text-ink-muted">{open.prep}</p>
        </div>
      ) : null}
    </div>
  );
}
