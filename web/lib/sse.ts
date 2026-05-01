"use client";

import { useEffect, useRef, useState } from "react";

export function useEventStream<T>(path: string, eventName: string = "trace") {
  const [last, setLast] = useState<T | null>(null);
  const [open, setOpen] = useState(false);
  const ref = useRef<EventSource | null>(null);

  useEffect(() => {
    const es = new EventSource(path);
    ref.current = es;
    es.onopen = () => setOpen(true);
    es.onerror = () => setOpen(false);
    const onMessage = (ev: MessageEvent) => {
      try {
        setLast(JSON.parse(ev.data) as T);
      } catch {
        // ignore
      }
    };
    es.addEventListener(eventName, onMessage);
    return () => {
      es.removeEventListener(eventName, onMessage);
      es.close();
    };
  }, [path, eventName]);

  return { last, open };
}
