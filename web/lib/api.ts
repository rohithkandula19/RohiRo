// thin client for the fastapi backend.
// next.js rewrites /api/* to localhost:8000, so we use relative paths.

export async function get<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path} ${res.status}`);
  return (await res.json()) as T;
}

export async function post<T, B = unknown>(path: string, body: B): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} ${res.status}`);
  return (await res.json()) as T;
}

export async function put<T, B = unknown>(path: string, body: B): Promise<T> {
  const res = await fetch(path, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} ${res.status}`);
  return (await res.json()) as T;
}

export type ChatTurn = { role: "user" | "assistant"; content: string };

export async function chatOnce(text: string, sessionId?: string) {
  return post<{ session_id: string; text: string; elapsed_ms: number }>(
    "/api/chat",
    { text, session_id: sessionId }
  );
}

export type StreamEvent =
  | { type: "stage"; name: string; text: string }
  | { type: "trace"; kind: string; [k: string]: unknown }
  | { type: "final"; text: string; elapsed_ms: number; domains: string[]; session_id: string };

export async function chatStream(
  text: string,
  history: ChatTurn[],
  onEvent: (e: StreamEvent) => void,
  sessionId?: string,
): Promise<void> {
  const res = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ text, history, session_id: sessionId }),
  });
  if (!res.ok || !res.body) throw new Error("stream failed");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const chunk = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      const dataLine = chunk
        .split("\n")
        .find((l) => l.startsWith("data:"));
      if (!dataLine) continue;
      const json = dataLine.slice(5).trim();
      if (!json) continue;
      try {
        onEvent(JSON.parse(json) as StreamEvent);
      } catch {
        // ignore parse errors, the stream is best effort.
      }
    }
  }
}
