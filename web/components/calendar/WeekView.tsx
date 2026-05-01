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

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

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
          <div key={d} className="card min-h-[180px]">
            <div className="kicker">{d}</div>
            <div className="mt-2 space-y-2">
              {events
                .filter((e) => new Date(e.start).getDay() === ((i + 1) % 7))
                .map((e) => (
                  <button
                    key={e.id}
                    onClick={() => setOpen(e)}
                    className="block w-full rounded-button border border-hair border-line-subtle p-2 text-left hover:bg-accent-soft"
                  >
                    <div className="kicker">
                      {new Date(e.start).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}
                    </div>
                    <div className="mt-1 text-[13px] text-ink">{e.title}</div>
                  </button>
                ))}
            </div>
          </div>
        ))}
      </div>

      {open ? (
        <div className="mt-6 card max-w-2xl">
          <div className="kicker">prep brief</div>
          <h3 className="mt-2 font-serif text-[20px]">{open.title}</h3>
          <div className="mt-1 text-[12px] text-ink-subtle">
            {open.attendees.join(", ")}
          </div>
          <p className="mt-4 text-[14px] leading-7 text-ink">{open.prep}</p>
          <button onClick={() => setOpen(null)} className="btn-secondary mt-4">
            close
          </button>
        </div>
      ) : null}
    </div>
  );
}
