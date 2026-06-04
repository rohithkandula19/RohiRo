"use client";

import { Command } from "cmdk";
import * as Dialog from "@radix-ui/react-dialog";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { chatStream, type ChatTurn, type StreamEvent } from "@/lib/api";

type Ctx = { open: () => void; close: () => void; isOpen: boolean };

const CommandPaletteContext = createContext<Ctx | null>(null);

export function useCommandPalette() {
  const ctx = useContext(CommandPaletteContext);
  if (!ctx) throw new Error("useCommandPalette outside provider");
  return ctx;
}

const QUICK = [
  { label: "Overview", path: "/overview" },
  { label: "Inbox", path: "/inbox" },
  { label: "Calendar", path: "/calendar" },
  { label: "Code", path: "/code" },
  { label: "Jobs", path: "/jobs" },
  { label: "Research", path: "/research" },
  { label: "Memory", path: "/memory" },
  { label: "Files", path: "/files" },
  { label: "Health", path: "/health" },
  { label: "Finance", path: "/finance" },
  { label: "Settings", path: "/settings" },
];

export function CommandPaletteProvider({ children }: { children: React.ReactNode }) {
  const [isOpen, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [chat, setChat] = useState<ChatTurn[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [stage, setStage] = useState<string>("");
  const sessionRef = useRef<string | undefined>();
  const router = useRouter();

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const submit = useCallback(async () => {
    const q = text.trim();
    if (!q) return;
    const next: ChatTurn[] = [...chat, { role: "user", content: q }];
    setChat(next); setText(""); setStreaming(true); setStage("thinking");
    try {
      await chatStream(q, chat, (e: StreamEvent) => {
        if (e.type === "stage") setStage(e.text);
        if (e.type === "final") {
          setChat([...next, { role: "assistant", content: e.text }]);
          sessionRef.current = e.session_id;
          setStreaming(false);
        }
      }, sessionRef.current);
    } catch {
      setChat([...next, { role: "assistant", content: "couldn't reach the api. is it running on :8000?" }]);
      setStreaming(false);
    }
  }, [text, chat]);

  return (
    <CommandPaletteContext.Provider value={{ open: () => setOpen(true), close: () => setOpen(false), isOpen }}>
      {children}
      <Dialog.Root open={isOpen} onOpenChange={setOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-black/30 backdrop-blur-[2px]" />
          <Dialog.Content className="fixed left-1/2 top-[14vh] z-50 w-[min(620px,92vw)] -translate-x-1/2 overflow-hidden rounded-[10px] border border-line bg-surface shadow-md">
            <Dialog.Title className="sr-only">Ask ro</Dialog.Title>
            <Command label="ro command palette" className="flex flex-col">
              <div className="flex items-center gap-2 border-b border-line px-3.5 py-2.5">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-ink-subtle"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
                <Command.Input
                  value={text}
                  onValueChange={setText}
                  onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); void submit(); } }}
                  placeholder="Ask ro anything, or jump to a page…"
                  className="flex-1 bg-transparent text-[14px] text-ink outline-none placeholder:text-ink-subtle"
                />
                <kbd>↵</kbd>
              </div>

              {streaming ? (
                <div className="flex items-center gap-2 border-b border-line px-3.5 py-2 text-[12px] text-ink-muted">
                  <span className="dot dot-live" />
                  <span>{stage || "working"}</span>
                </div>
              ) : null}

              {chat.length > 0 && !streaming ? (
                <div className="max-h-72 space-y-3 overflow-auto px-3.5 py-3 text-[13px]">
                  {chat.slice(-6).map((m, i) => (
                    <div key={i}>
                      <div className="label">{m.role === "user" ? "You" : "ro"}</div>
                      <div className="mt-0.5 whitespace-pre-wrap text-ink">{m.content}</div>
                    </div>
                  ))}
                </div>
              ) : null}

              {!chat.length && !streaming ? (
                <Command.List className="max-h-80 overflow-auto py-1.5">
                  <Command.Empty className="px-4 py-6 text-center text-[12px] text-ink-subtle">
                    press enter to ask
                  </Command.Empty>
                  <Command.Group heading="Jump to" className="px-1">
                    {QUICK.map((q) => (
                      <Command.Item
                        key={q.path}
                        onSelect={() => { setOpen(false); router.push(q.path); }}
                        className="mx-1 flex cursor-pointer items-center justify-between rounded-[5px] px-3 py-1.5 text-[13px] aria-selected:bg-accent-soft aria-selected:text-accent"
                      >
                        <span>{q.label}</span>
                        <span className="font-mono text-[10.5px] text-ink-subtle">{q.path}</span>
                      </Command.Item>
                    ))}
                  </Command.Group>
                </Command.List>
              ) : null}
            </Command>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </CommandPaletteContext.Provider>
  );
}
