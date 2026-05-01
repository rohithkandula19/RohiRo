"use client";

import { Command } from "cmdk";
import * as Dialog from "@radix-ui/react-dialog";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { chatStream, type ChatTurn, type StreamEvent } from "@/lib/api";

type Ctx = {
  open: () => void;
  close: () => void;
  isOpen: boolean;
};

const CommandPaletteContext = createContext<Ctx | null>(null);

export function useCommandPalette() {
  const ctx = useContext(CommandPaletteContext);
  if (!ctx) throw new Error("useCommandPalette outside provider");
  return ctx;
}

const QUICK = [
  { label: "go to overview", path: "/overview" },
  { label: "go to inbox", path: "/inbox" },
  { label: "go to calendar", path: "/calendar" },
  { label: "go to code", path: "/code" },
  { label: "go to jobs", path: "/jobs" },
  { label: "go to research", path: "/research" },
  { label: "go to memory", path: "/memory" },
  { label: "go to files", path: "/files" },
  { label: "go to health", path: "/health" },
  { label: "go to finance", path: "/finance" },
  { label: "go to settings", path: "/settings" },
];

export function CommandPaletteProvider({ children }: { children: React.ReactNode }) {
  const [isOpen, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [chat, setChat] = useState<ChatTurn[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [streamText, setStreamText] = useState("");
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

    // route shortcut
    const routeMatch = QUICK.find((r) => r.label === q);
    if (routeMatch) {
      setText("");
      setOpen(false);
      router.push(routeMatch.path);
      return;
    }

    const next: ChatTurn[] = [...chat, { role: "user", content: q }];
    setChat(next);
    setText("");
    setStreaming(true);
    setStreamText("");
    setStage("thinking");

    try {
      await chatStream(q, chat, (e: StreamEvent) => {
        if (e.type === "stage") setStage(e.text);
        if (e.type === "final") {
          setChat([...next, { role: "assistant", content: e.text }]);
          setStreamText(e.text);
          sessionRef.current = e.session_id;
          setStreaming(false);
        }
      }, sessionRef.current);
    } catch (err) {
      setChat([
        ...next,
        { role: "assistant", content: "couldn't reach the api. is it running on :8000?" },
      ]);
      setStreaming(false);
    }
  }, [text, chat, router]);

  return (
    <CommandPaletteContext.Provider
      value={{
        open: () => setOpen(true),
        close: () => setOpen(false),
        isOpen,
      }}
    >
      {children}
      <Dialog.Root open={isOpen} onOpenChange={setOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm" />
          <Dialog.Content className="fixed left-1/2 top-[12vh] z-50 w-[min(640px,90vw)] -translate-x-1/2 rounded-card border border-hair border-line bg-surface shadow-xl">
            <Dialog.Title className="sr-only">talk to ro</Dialog.Title>
            <Command label="ro command palette" className="flex flex-col">
              <div className="border-b border-hair border-line-subtle px-4 py-3">
                <div className="kicker">talk to ro</div>
                <Command.Input
                  value={text}
                  onValueChange={setText}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      void submit();
                    }
                  }}
                  placeholder="ask anything, or type a page name"
                  className="mt-1 w-full bg-transparent text-[15px] outline-none placeholder:text-ink-subtle"
                />
              </div>

              {streaming ? (
                <div className="flex items-center gap-2 px-4 py-3 text-[12px] text-ink-muted">
                  <span className="dot inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
                  <span>{stage || "working"}</span>
                </div>
              ) : null}

              {chat.length > 0 && !streaming ? (
                <div className="max-h-64 space-y-3 overflow-auto px-4 py-3 text-[13px]">
                  {chat.slice(-6).map((m, i) => (
                    <div key={i} className="space-y-1">
                      <div className="kicker">{m.role}</div>
                      <div className="whitespace-pre-wrap text-ink">{m.content}</div>
                    </div>
                  ))}
                </div>
              ) : null}

              {!chat.length && !streaming ? (
                <Command.List className="max-h-72 overflow-auto p-2">
                  <Command.Empty className="px-3 py-6 text-center text-[12px] text-ink-subtle">
                    press enter to ask ro
                  </Command.Empty>
                  <Command.Group heading="quick jump" className="px-2 py-2">
                    {QUICK.map((q) => (
                      <Command.Item
                        key={q.path}
                        onSelect={() => {
                          setOpen(false);
                          router.push(q.path);
                        }}
                        className="flex cursor-pointer items-center justify-between rounded-button px-3 py-2 text-[13px] aria-selected:bg-accent-soft"
                      >
                        <span>{q.label}</span>
                        <span className="kicker">{q.path}</span>
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
