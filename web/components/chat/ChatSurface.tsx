"use client";

import { useEffect, useRef, useState } from "react";
import { chatStream, type ChatTurn, type StreamEvent, type ToolCall } from "@/lib/api";
import { useVoice } from "@/components/chat/useVoice";

type AssistantMsg = {
  role: "assistant";
  content: string;
  tool_calls?: ToolCall[];
  actions?: string[];
};
type UserMsg = { role: "user"; content: string };
type Msg = UserMsg | AssistantMsg;

const EXAMPLES = [
  "Show me unread emails from this week",
  "What's on my calendar tomorrow?",
  "Reply to Sarah saying Tuesday works",
  "Find 90 minutes free this week",
  "Send Mom a text saying I'll call tonight",
  "DM Alex on slack about the deploy",
  "Show my recent github repos",
  "Summarize what changed in rohflow",
];

export function ChatSurface() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [stage, setStage] = useState<string>("");
  const sessionRef = useRef<string | undefined>();
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const voice = useVoice();

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, stage]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  async function send(text: string) {
    const q = text.trim();
    if (!q || streaming) return;
    const history: ChatTurn[] = messages.map((m) => ({ role: m.role, content: m.content }));
    const next: Msg[] = [...messages, { role: "user", content: q }];
    setMessages(next);
    setInput("");
    setStreaming(true);
    setStage("thinking");

    try {
      await chatStream(
        q,
        history,
        (e: StreamEvent) => {
          if (e.type === "stage") setStage(e.text);
          if (e.type === "final") {
            setMessages([
              ...next,
              {
                role: "assistant",
                content: e.text,
                tool_calls: e.tool_calls,
                actions: e.actions,
              },
            ]);
            sessionRef.current = e.session_id;
            setStreaming(false);
            setStage("");
            void voice.speak(e.text);
          }
        },
        sessionRef.current,
      );
    } catch {
      setMessages([
        ...next,
        { role: "assistant", content: "i couldn't reach the api. is it running on :8000?" },
      ]);
      setStreaming(false);
      setStage("");
    }
  }

  function onKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send(input);
    }
  }

  async function toggleMic() {
    if (voice.status === "recording") {
      const text = await voice.stop();
      if (text) {
        // auto-send so the round-trip is mic press → release → ro replies
        await send(text);
      }
    } else {
      voice.stopSpeaking();
      await voice.start();
    }
  }

  // ⌘⇧R hotkey: toggle mic while the page is focused
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === "r") {
        e.preventDefault();
        void toggleMic();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [voice.status, input]);

  const empty = messages.length === 0 && !streaming;

  return (
    <div className="flex h-full flex-col">
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[720px] px-6 pb-32 pt-12">
          {empty ? (
            <div className="mt-24 text-center">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-[10px] bg-accent text-[20px] font-semibold text-accent-ink">
                r
              </div>
              <h1 className="mt-5 text-[26px] font-semibold tracking-tight text-ink">
                Hey Rohith. What should I do?
              </h1>
              <p className="mt-2 text-[13.5px] text-ink-muted">
                I can read your email, draft replies, schedule things, and more. Just ask.
              </p>
              <StatsPill />

              <div className="mx-auto mt-10 grid max-w-[560px] grid-cols-1 gap-2 sm:grid-cols-2">
                {EXAMPLES.map((ex) => (
                  <button
                    key={ex}
                    onClick={() => send(ex)}
                    className="rounded-[8px] border border-line bg-surface px-3.5 py-3 text-left text-[12.5px] text-ink-muted transition-all hover:bg-surface-hover hover:text-ink"
                  >
                    {ex}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-8">
              {messages.map((m, i) => <Message key={i} msg={m} />)}
              {streaming ? <StreamingIndicator stage={stage} /> : null}
            </div>
          )}
        </div>
      </div>

      <div className="border-t border-line bg-bg">
        <div className="mx-auto max-w-[720px] px-6 py-4">
          <div className="relative rounded-[12px] border border-line bg-surface shadow-sm transition-shadow focus-within:border-line-strong focus-within:shadow-md">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKey}
              placeholder="Ask ro to do anything…"
              rows={1}
              className="w-full resize-none bg-transparent px-4 py-3.5 pr-12 text-[14px] text-ink outline-none placeholder:text-ink-subtle"
              style={{ minHeight: "52px", maxHeight: "200px" }}
              onInput={(e) => {
                const t = e.currentTarget;
                t.style.height = "auto";
                t.style.height = Math.min(200, t.scrollHeight) + "px";
              }}
            />
            <div className="absolute bottom-2.5 right-2.5 flex items-center gap-1.5">
              <button
                onClick={toggleMic}
                disabled={voice.status === "transcribing"}
                className={
                  "flex h-8 w-8 items-center justify-center rounded-[7px] border transition-colors " +
                  (voice.status === "recording"
                    ? "border-danger bg-danger/10 text-danger animate-pulse"
                    : voice.status === "transcribing"
                    ? "border-line bg-surface-hover text-ink-subtle"
                    : "border-line bg-surface text-ink-muted hover:bg-surface-hover hover:text-ink")
                }
                aria-label={voice.status === "recording" ? "stop recording" : "record"}
                title={voice.status === "recording" ? "Stop (⌘⇧R)" : "Talk to ro (⌘⇧R)"}
              >
                {voice.status === "recording" ? (
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><rect x="5" y="5" width="14" height="14" rx="2"/></svg>
                ) : voice.status === "transcribing" ? (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="animate-spin"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>
                ) : (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>
                )}
              </button>
              <button
                onClick={() => send(input)}
                disabled={!input.trim() || streaming}
                className="flex h-8 w-8 items-center justify-center rounded-[7px] bg-accent text-accent-ink transition-opacity disabled:opacity-30 enabled:hover:bg-accent-hover"
                aria-label="send"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path d="M12 19V5M5 12l7-7 7 7" />
                </svg>
              </button>
            </div>
          </div>
          <div className="mt-2 flex items-center justify-between text-[11px] text-ink-subtle">
            <span>
              ro acts on your behalf and asks before sending anything outbound.
            </span>
            <div className="flex items-center gap-3">
              <button
                onClick={() => {
                  voice.setTtsOn(!voice.ttsOn);
                  if (voice.ttsOn) voice.stopSpeaking();
                }}
                className={"flex items-center gap-1 " + (voice.ttsOn ? "text-ink-muted hover:text-ink" : "text-ink-subtle hover:text-ink-muted")}
                title={voice.ttsOn ? "Voice replies on" : "Voice replies off"}
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M11 5L6 9H2v6h4l5 4V5z"/>
                  {voice.ttsOn ? <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/> : <line x1="23" y1="9" x2="17" y2="15"/>}
                  {!voice.ttsOn ? <line x1="17" y1="9" x2="23" y2="15"/> : null}
                </svg>
                <span>voice replies {voice.ttsOn ? "on" : "off"}</span>
              </button>
              <span>
                <kbd>⌘</kbd>+<kbd>⇧</kbd>+<kbd>R</kbd> talk · <kbd>↵</kbd> send
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Message({ msg }: { msg: Msg }) {
  if (msg.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-[12px] rounded-br-[3px] bg-accent px-3.5 py-2.5 text-[13.5px] leading-6 text-accent-ink">
          {msg.content}
        </div>
      </div>
    );
  }

  const calls = msg.tool_calls ?? [];
  const RICH_TOOLS = new Set([
    "gmail.search",
    "gmail.draft_reply",
    "gmail.draft_new",
    "calendar.list",
    "calendar.find_free",
    "calendar.draft_event",
    "calendar.prep_brief",
    "github.list_repos",
    "github.list_prs",
    "github.commits",
    "github.summary",
    "slack.history",
    "slack.search",
    "slack.list_dms",
    "slack.draft",
    "imessage.history",
    "imessage.threads",
    "imessage.draft",
    "telegram.draft",
    "whatsapp.draft",
    "shell.draft",
    "file.draft",
    "web.draft",
    "browser.draft",
    "browser_step.draft",
    "vision.draft",
    "drive.list",
    "drive.search",
    "drive.read",
    "drive.summary",
    "notion.search",
    "notion.read",
    "notion.summary",
    "notion.create_draft",
    "notion.append_draft",
    "schedule.draft",
    "schedule.list",
    "linear.list",
    "linear.search",
    "linear.read",
    "linear.projects",
    "linear.create_draft",
    "linear.comment_draft",
  ]);
  const hasRichCard = calls.some((c) => RICH_TOOLS.has(c.tool));

  return (
    <div className="flex gap-3">
      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-[7px] bg-accent text-[11px] font-semibold text-accent-ink">
        r
      </div>
      <div className="min-w-0 flex-1 space-y-3">
        {!hasRichCard ? (
          <div className="whitespace-pre-wrap text-[14px] leading-[1.65] text-ink">{msg.content}</div>
        ) : null}
        {calls.map((c, i) => (
          <ToolCallCard key={i} call={c} actionId={msg.actions?.[i]} />
        ))}
      </div>
    </div>
  );
}

function ToolCallCard({ call, actionId }: { call: ToolCall; actionId?: string }) {
  if (call.tool === "gmail.search") return <GmailListCard call={call} />;
  if (call.tool === "gmail.draft_reply" || call.tool === "gmail.draft_new")
    return <GmailDraftCard call={call} actionId={actionId} />;
  if (call.tool === "calendar.list" || call.tool === "calendar.prep_brief")
    return <CalendarEventsCard call={call} />;
  if (call.tool === "calendar.find_free") return <FreeSlotsCard call={call} />;
  if (call.tool === "calendar.draft_event")
    return <CalendarDraftCard call={call} actionId={actionId} />;
  if (call.tool === "github.list_repos") return <GithubReposCard call={call} />;
  if (call.tool === "github.list_prs") return <GithubPRsCard call={call} />;
  if (call.tool === "github.commits") return <GithubCommitsCard call={call} />;
  if (call.tool === "github.summary") return <GithubSummaryCard call={call} />;
  if (call.tool === "slack.history") return <SlackHistoryCard call={call} />;
  if (call.tool === "slack.search") return <SlackSearchCard call={call} />;
  if (call.tool === "slack.list_dms") return <SlackDmsCard call={call} />;
  if (call.tool === "slack.draft") return <SlackDraftCard call={call} actionId={actionId} />;
  if (call.tool === "imessage.history") return <IMessageHistoryCard call={call} />;
  if (call.tool === "imessage.threads") return <IMessageThreadsCard call={call} />;
  if (call.tool === "imessage.draft") return <IMessageDraftCard call={call} actionId={actionId} />;
  if (call.tool === "telegram.draft") return <TelegramDraftCard call={call} actionId={actionId} />;
  if (call.tool === "whatsapp.draft") return <WhatsAppDraftCard call={call} actionId={actionId} />;
  if (call.tool === "shell.draft") return <ShellDraftCard call={call} actionId={actionId} />;
  if (call.tool === "file.draft") return <FileDraftCard call={call} actionId={actionId} />;
  if (call.tool === "web.draft") return <WebDraftCard call={call} actionId={actionId} />;
  if (call.tool === "browser.draft") return <BrowserDraftCard call={call} actionId={actionId} />;
  if (call.tool === "browser_step.draft") return <BrowserStepCard call={call} actionId={actionId} />;
  if (call.tool === "vision.draft") return <VisionDraftCard call={call} actionId={actionId} />;
  if (call.tool === "drive.list" || call.tool === "drive.search") return <DriveListCard call={call} />;
  if (call.tool === "drive.read") return <DriveReadCard call={call} />;
  if (call.tool === "drive.summary") return <DriveSummaryCard call={call} />;
  if (call.tool === "notion.search") return <NotionSearchCard call={call} />;
  if (call.tool === "notion.read") return <NotionReadCard call={call} />;
  if (call.tool === "notion.summary") return <NotionSummaryCard call={call} />;
  if (call.tool === "notion.create_draft") return <NotionCreateCard call={call} actionId={actionId} />;
  if (call.tool === "notion.append_draft") return <NotionAppendCard call={call} actionId={actionId} />;
  if (call.tool === "schedule.draft") return <ScheduleDraftCard call={call} actionId={actionId} />;
  if (call.tool === "schedule.list") return <ScheduleListCard call={call} />;
  if (call.tool === "linear.list" || call.tool === "linear.search") return <LinearIssuesCard call={call} />;
  if (call.tool === "linear.read") return <LinearIssueCard call={call} />;
  if (call.tool === "linear.projects") return <LinearProjectsCard call={call} />;
  if (call.tool === "linear.create_draft") return <LinearCreateCard call={call} actionId={actionId} />;
  if (call.tool === "linear.comment_draft") return <LinearCommentCard call={call} actionId={actionId} />;
  return null;
}

// ─── linear ─────────────────────────────────────────────────────────────

function priorityChip(p: number) {
  if (p === 1) return <span className="chip chip-bad">urgent</span>;
  if (p === 2) return <span className="chip chip-warn">high</span>;
  if (p === 3) return <span className="chip">medium</span>;
  if (p === 4) return <span className="chip">low</span>;
  return null;
}

function LinearIssuesCard({ call }: { call: ToolCall }) {
  type I = { identifier: string; title: string; state: string; priority: number; url: string; assignee?: string; team?: string };
  const issues = (Array.isArray(call.result) ? call.result : []) as I[];
  const isSearch = call.tool === "linear.search";
  const q = (call.args as { query?: string } | undefined)?.query;
  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line px-3.5 py-2">
        <div className="text-[12px] font-medium text-ink">
          Linear · {issues.length} issue{issues.length === 1 ? "" : "s"}
        </div>
        {isSearch && q ? <span className="text-[11px] text-ink-subtle">{q}</span> : null}
      </div>
      <ul>
        {issues.map((i) => (
          <li key={i.identifier} className="flex items-start gap-3 border-b border-line px-3.5 py-2 last:border-b-0 hover:bg-surface-hover">
            <a href={i.url} target="_blank" rel="noreferrer" className="font-mono text-[11.5px] text-accent hover:text-accent-hover">
              {i.identifier}
            </a>
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline gap-2">
                <span className="truncate text-[13px] text-ink">{i.title}</span>
                <span className="ml-auto shrink-0"><span className="chip">{i.state}</span></span>
              </div>
              <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-ink-subtle">
                {priorityChip(i.priority)}
                {i.team ? <span>· {i.team}</span> : null}
                {i.assignee ? <span>· {i.assignee}</span> : null}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function LinearIssueCard({ call }: { call: ToolCall }) {
  const i = call.result as {
    identifier?: string; title?: string; state?: string; priority?: number;
    url?: string; team?: string; project?: string; assignee?: string;
    description?: string;
  } | undefined;
  if (!i) return null;
  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line px-3.5 py-2">
        <a href={i.url} target="_blank" rel="noreferrer" className="font-mono text-[12px] font-medium text-accent hover:text-accent-hover">
          {i.identifier}
        </a>
        <span className="chip">{i.state}</span>
      </div>
      <div className="px-3.5 py-3">
        <div className="text-[14px] font-medium text-ink">{i.title}</div>
        <div className="mt-1 flex items-center gap-2 text-[11.5px] text-ink-subtle">
          {priorityChip(i.priority ?? 0)}
          {i.team ? <span>· {i.team}</span> : null}
          {i.project ? <span>· {i.project}</span> : null}
          {i.assignee ? <span>· {i.assignee}</span> : null}
        </div>
        {i.description ? (
          <div className="mt-3 whitespace-pre-wrap rounded-[6px] bg-surface-hover p-3 text-[12.5px] text-ink-muted">
            {i.description}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function LinearProjectsCard({ call }: { call: ToolCall }) {
  type P = { name: string; state: string; url: string };
  const ps = (Array.isArray(call.result) ? call.result : []) as P[];
  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="border-b border-line px-3.5 py-2 text-[12px] font-medium text-ink">Linear · projects</div>
      <ul>
        {ps.map((p, i) => (
          <li key={i} className="flex items-center justify-between border-b border-line px-3.5 py-2 last:border-b-0">
            <a href={p.url} target="_blank" rel="noreferrer" className="text-[12.5px] text-ink hover:text-accent">{p.name}</a>
            <span className="chip">{p.state}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function LinearCreateCard({ call, actionId }: { call: ToolCall; actionId?: string }) {
  const r = call.result as { team_key?: string; title?: string; description?: string } | undefined;
  const { state, result, err, decide } = useApproval(actionId);
  const out = (result as { identifier?: string; url?: string }) ?? {};
  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line bg-warning/[0.05] px-3.5 py-2">
        <div className="flex items-center gap-2">
          <span className="chip chip-warn">New issue</span>
          <span className="font-mono text-[12px] text-ink-muted">{r?.team_key}</span>
        </div>
        <span className="text-[11px] text-ink-subtle">
          {state === "done" ? `${out.identifier ?? "created"} ✓` :
           state === "rejected" ? "rejected" :
           state === "running" ? "creating…" :
           state === "error" ? "error" : "needs approval"}
        </span>
      </div>
      <div className="px-3.5 py-3">
        <div className="text-[13px] font-medium text-ink">{r?.title}</div>
        {r?.description ? (
          <pre className="mt-2 whitespace-pre-wrap rounded-[6px] border-l-2 border-warning bg-warning/[0.04] px-3 py-2 text-[12.5px] text-ink">{r.description}</pre>
        ) : null}
      </div>
      {state === "pending" ? (
        <div className="flex items-center gap-2 border-t border-line px-3.5 py-2.5">
          <button onClick={() => decide("approved")} className="btn btn-primary">Create issue</button>
          <button onClick={() => decide("rejected")} className="btn btn-danger">Reject</button>
        </div>
      ) : null}
      {state === "done" && out.url ? (
        <div className="border-t border-line px-3.5 py-2 text-[12px]">
          <a href={out.url} target="_blank" rel="noreferrer" className="text-accent hover:text-accent-hover">open in linear →</a>
        </div>
      ) : null}
      {state === "error" ? (
        <div className="border-t border-line px-3.5 py-2 text-[12px] text-danger">Error: {err}</div>
      ) : null}
    </div>
  );
}

function LinearCommentCard({ call, actionId }: { call: ToolCall; actionId?: string }) {
  const r = call.result as { identifier?: string; body?: string } | undefined;
  const [body, setBody] = useState(r?.body ?? "");
  const [editing, setEditing] = useState(false);
  const { state, result, err, decide } = useApproval(actionId);
  const out = (result as { url?: string; issue?: string }) ?? {};
  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line bg-warning/[0.05] px-3.5 py-2">
        <div className="flex items-center gap-2">
          <span className="chip chip-warn">Comment</span>
          <span className="font-mono text-[12px] text-ink-muted">{r?.identifier}</span>
        </div>
        <span className="text-[11px] text-ink-subtle">
          {state === "done" ? "posted ✓" :
           state === "rejected" ? "rejected" :
           state === "running" ? "posting…" :
           state === "error" ? "error" : "needs approval"}
        </span>
      </div>
      <div className="px-3.5 py-3">
        {editing ? (
          <textarea value={body} onChange={(e) => setBody(e.target.value)}
            className="w-full min-h-[120px] resize-y rounded-[6px] border border-line bg-bg p-3 text-[13px] leading-6 text-ink outline-none focus:border-accent" />
        ) : (
          <pre className="overflow-x-auto whitespace-pre-wrap rounded-[6px] border-l-2 border-warning bg-warning/[0.04] px-3 py-2.5 text-[13px] leading-6 text-ink">{body}</pre>
        )}
      </div>
      {state === "pending" ? (
        <div className="flex items-center gap-2 border-t border-line px-3.5 py-2.5">
          <button onClick={() => decide("approved", editing ? body : undefined)} className="btn btn-primary">
            {editing ? "Save & post" : "Post comment"}
          </button>
          <button onClick={() => setEditing((v) => !v)} className="btn">{editing ? "Cancel edit" : "Edit"}</button>
          <button onClick={() => decide("rejected")} className="btn btn-danger">Reject</button>
        </div>
      ) : null}
      {state === "done" && out.url ? (
        <div className="border-t border-line px-3.5 py-2 text-[12px]">
          <a href={out.url} target="_blank" rel="noreferrer" className="text-accent hover:text-accent-hover">open in linear →</a>
        </div>
      ) : null}
      {state === "error" ? (
        <div className="border-t border-line px-3.5 py-2 text-[12px] text-danger">Error: {err}</div>
      ) : null}
    </div>
  );
}

// ─── scheduler ──────────────────────────────────────────────────────────

function ScheduleDraftCard({ call, actionId }: { call: ToolCall; actionId?: string }) {
  const r = call.result as {
    kind?: string; spec?: string; title?: string; text?: string;
    timezone?: string; next_at?: string; next_at_human?: string;
  } | undefined;
  const { state, result, err, decide } = useApproval(actionId);
  const out = (result as { schedule_id?: string; next_at?: string }) ?? {};
  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line bg-warning/[0.05] px-3.5 py-2">
        <div className="flex items-center gap-2">
          <span className="chip chip-warn">Schedule {r?.kind}</span>
          <span className="text-[12px] text-ink-muted">{r?.title}</span>
        </div>
        <span className="text-[11px] text-ink-subtle">
          {state === "done" ? "scheduled ✓" :
           state === "rejected" ? "rejected" :
           state === "running" ? "scheduling…" :
           state === "error" ? "error" : "needs approval"}
        </span>
      </div>
      <div className="space-y-1.5 px-3.5 py-3 text-[12.5px]">
        <div className="text-ink-muted">
          <span className="text-ink-subtle">When:</span>{" "}
          {r?.kind === "cron"
            ? <><span className="font-mono">{r?.spec}</span> <span className="text-ink-subtle">({r?.timezone}) · first fire {r?.next_at_human}</span></>
            : <>{r?.next_at_human}</>}
        </div>
        <div className="text-ink-muted">
          <span className="text-ink-subtle">Does:</span> <span className="text-ink">{r?.text}</span>
        </div>
      </div>
      {state === "pending" ? (
        <div className="flex items-center gap-2 border-t border-line px-3.5 py-2.5">
          <button onClick={() => decide("approved")} className="btn btn-primary">Schedule it</button>
          <button onClick={() => decide("rejected")} className="btn btn-danger">Cancel</button>
        </div>
      ) : null}
      {state === "error" ? (
        <div className="border-t border-line px-3.5 py-2 text-[12px] text-danger">Error: {err}</div>
      ) : null}
    </div>
  );
}

function ScheduleListCard({ call }: { call: ToolCall }) {
  type S = { id: string; kind: string; spec: string; title: string; text: string;
             enabled: boolean; next_at: string; last_run_at?: string | null };
  const items = (Array.isArray(call.result) ? call.result : []) as S[];

  async function cancel(id: string) {
    await fetch(`/api/schedules/${id}`, { method: "DELETE" });
    // optimistic: hide the row
    const el = document.getElementById(`sched-${id}`);
    if (el) el.style.opacity = "0.3";
  }

  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="border-b border-line px-3.5 py-2 text-[12px] font-medium text-ink">
        Schedules · {items.length}
      </div>
      <ul>
        {items.map((s) => (
          <li
            key={s.id}
            id={`sched-${s.id}`}
            className="flex items-center justify-between gap-3 border-b border-line px-3.5 py-2.5 last:border-b-0"
          >
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline gap-2">
                <span className="chip">{s.kind}</span>
                <span className="text-[13px] font-medium text-ink">{s.title}</span>
                {!s.enabled ? <span className="chip">off</span> : null}
              </div>
              <div className="mt-0.5 line-clamp-1 text-[12px] text-ink-muted">{s.text}</div>
              <div className="text-[11px] text-ink-subtle">
                next {new Date(s.next_at).toLocaleString()} · {s.kind === "cron" ? <span className="font-mono">{s.spec}</span> : null}
              </div>
            </div>
            <button onClick={() => cancel(s.id)} className="btn btn-ghost px-2 py-1 text-[11px]">Cancel</button>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ─── notion ────────────────────────────────────────────────────────────

function NotionSearchCard({ call }: { call: ToolCall }) {
  type H = { object_kind: string; title: string; url: string; icon?: string; last_edited_at?: string };
  const hits = (Array.isArray(call.result) ? call.result : []) as H[];
  const q = (call.args as { query?: string } | undefined)?.query;
  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line px-3.5 py-2">
        <div className="text-[12px] font-medium text-ink">Notion · {hits.length} hit{hits.length === 1 ? "" : "s"}</div>
        {q ? <span className="text-[11px] text-ink-subtle">{q}</span> : null}
      </div>
      <ul>
        {hits.map((h, i) => (
          <li key={i} className="flex items-center justify-between border-b border-line px-3.5 py-2 last:border-b-0 hover:bg-surface-hover">
            <a href={h.url} target="_blank" rel="noreferrer" className="min-w-0 flex-1 truncate text-[12.5px] text-ink hover:text-accent">
              {h.icon ? <span className="mr-1">{h.icon}</span> : null}{h.title}
            </a>
            <span className="chip">{h.object_kind}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function NotionReadCard({ call }: { call: ToolCall }) {
  const r = call.result as { title?: string; url?: string; icon?: string; content?: string } | undefined;
  if (!r) return null;
  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line px-3.5 py-2">
        <a href={r.url} target="_blank" rel="noreferrer" className="text-[12.5px] font-medium text-ink hover:text-accent">
          {r.icon ? <span className="mr-1">{r.icon}</span> : null}{r.title}
        </a>
        <span className="chip">notion</span>
      </div>
      <pre className="max-h-[320px] overflow-auto whitespace-pre-wrap px-3.5 py-3 text-[12.5px] leading-6 text-ink">{r.content}</pre>
    </div>
  );
}

function NotionSummaryCard({ call }: { call: ToolCall }) {
  const r = call.result as { title?: string; url?: string; icon?: string; summary?: string } | undefined;
  if (!r) return null;
  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line px-3.5 py-2">
        <a href={r.url} target="_blank" rel="noreferrer" className="text-[12.5px] font-medium text-ink hover:text-accent">
          {r.icon ? <span className="mr-1">{r.icon}</span> : null}{r.title}
        </a>
        <span className="chip chip-accent">summary</span>
      </div>
      <div className="whitespace-pre-wrap px-3.5 py-3 text-[13px] leading-6 text-ink">{r.summary}</div>
    </div>
  );
}

function NotionCreateCard({ call, actionId }: { call: ToolCall; actionId?: string }) {
  const r = call.result as { parent?: string; parent_url?: string; title?: string; body?: string } | undefined;
  const [body, setBody] = useState(r?.body ?? "");
  const [editing, setEditing] = useState(false);
  const { state, result, err, decide } = useApproval(actionId);
  const out = (result as { page_id?: string; url?: string }) ?? {};
  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line bg-warning/[0.05] px-3.5 py-2">
        <div className="flex items-center gap-2">
          <span className="chip chip-warn">New notion page</span>
          <span className="text-[12px] text-ink-muted">{r?.title} · under {r?.parent}</span>
        </div>
        <span className="text-[11px] text-ink-subtle">
          {state === "done" ? "created ✓" : state === "rejected" ? "rejected" : state === "running" ? "creating…" : state === "error" ? "error" : "needs approval"}
        </span>
      </div>
      <div className="px-3.5 py-3">
        {editing ? (
          <textarea value={body} onChange={(e) => setBody(e.target.value)}
            className="w-full min-h-[160px] resize-y rounded-[6px] border border-line bg-bg p-3 text-[13px] leading-6 text-ink outline-none focus:border-accent" />
        ) : (
          <pre className="overflow-x-auto whitespace-pre-wrap rounded-[6px] border-l-2 border-warning bg-warning/[0.04] px-3 py-2.5 text-[13px] leading-6 text-ink">{body}</pre>
        )}
      </div>
      {state === "pending" ? (
        <div className="flex items-center gap-2 border-t border-line px-3.5 py-2.5">
          <button onClick={() => decide("approved", editing ? body : undefined)} className="btn btn-primary">
            {editing ? "Save & create" : "Create page"}
          </button>
          <button onClick={() => setEditing((v) => !v)} className="btn">{editing ? "Cancel edit" : "Edit"}</button>
          <button onClick={() => decide("rejected")} className="btn btn-danger">Reject</button>
        </div>
      ) : null}
      {state === "done" && out.url ? (
        <div className="border-t border-line px-3.5 py-2 text-[12px]">
          <a href={out.url} target="_blank" rel="noreferrer" className="text-accent hover:text-accent-hover">open in notion →</a>
        </div>
      ) : null}
      {state === "error" ? (
        <div className="border-t border-line px-3.5 py-2 text-[12px] text-danger">Error: {err}</div>
      ) : null}
    </div>
  );
}

function NotionAppendCard({ call, actionId }: { call: ToolCall; actionId?: string }) {
  const r = call.result as { page_title?: string; page_url?: string; body?: string } | undefined;
  const [body, setBody] = useState(r?.body ?? "");
  const [editing, setEditing] = useState(false);
  const { state, result, err, decide } = useApproval(actionId);
  const out = (result as { appended?: number }) ?? {};
  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line bg-warning/[0.05] px-3.5 py-2">
        <div className="flex items-center gap-2">
          <span className="chip chip-warn">Append</span>
          <span className="text-[12px] text-ink-muted">{r?.page_title}</span>
        </div>
        <span className="text-[11px] text-ink-subtle">
          {state === "done" ? `${out.appended ?? 0} blocks added ✓` :
           state === "rejected" ? "rejected" :
           state === "running" ? "appending…" :
           state === "error" ? "error" : "needs approval"}
        </span>
      </div>
      <div className="px-3.5 py-3">
        {editing ? (
          <textarea value={body} onChange={(e) => setBody(e.target.value)}
            className="w-full min-h-[120px] resize-y rounded-[6px] border border-line bg-bg p-3 text-[13px] leading-6 text-ink outline-none focus:border-accent" />
        ) : (
          <pre className="overflow-x-auto whitespace-pre-wrap rounded-[6px] border-l-2 border-warning bg-warning/[0.04] px-3 py-2.5 text-[13px] leading-6 text-ink">{body}</pre>
        )}
      </div>
      {state === "pending" ? (
        <div className="flex items-center gap-2 border-t border-line px-3.5 py-2.5">
          <button onClick={() => decide("approved", editing ? body : undefined)} className="btn btn-primary">
            {editing ? "Save & append" : "Append"}
          </button>
          <button onClick={() => setEditing((v) => !v)} className="btn">{editing ? "Cancel edit" : "Edit"}</button>
          <button onClick={() => decide("rejected")} className="btn btn-danger">Reject</button>
        </div>
      ) : null}
      {state === "done" && r?.page_url ? (
        <div className="border-t border-line px-3.5 py-2 text-[12px]">
          <a href={r.page_url} target="_blank" rel="noreferrer" className="text-accent hover:text-accent-hover">open in notion →</a>
        </div>
      ) : null}
      {state === "error" ? (
        <div className="border-t border-line px-3.5 py-2 text-[12px] text-danger">Error: {err}</div>
      ) : null}
    </div>
  );
}

// ─── drive ──────────────────────────────────────────────────────────────

function DriveListCard({ call }: { call: ToolCall }) {
  type F = { file_id: string; name: string; mime_type: string; modified_at?: string; web_view?: string };
  const files = (Array.isArray(call.result) ? call.result : []) as F[];
  const isSearch = call.tool === "drive.search";
  const q = (call.args as { query?: string } | undefined)?.query;
  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line px-3.5 py-2">
        <div className="flex items-center gap-2 text-[12px]">
          <span className="font-medium text-ink">Drive</span>
          <span className="text-ink-muted">·</span>
          <span className="text-ink-muted">{files.length} file{files.length === 1 ? "" : "s"}</span>
        </div>
        {isSearch && q ? <span className="text-[11px] text-ink-subtle">{q}</span> : null}
      </div>
      <ul>
        {files.map((f) => (
          <li key={f.file_id} className="flex items-center justify-between border-b border-line px-3.5 py-2 last:border-b-0 hover:bg-surface-hover">
            <a
              href={f.web_view || "#"}
              target="_blank"
              rel="noreferrer"
              className="min-w-0 flex-1 truncate text-[12.5px] text-ink hover:text-accent"
            >
              {f.name}
            </a>
            <span className="chip">{labelMime(f.mime_type)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function DriveReadCard({ call }: { call: ToolCall }) {
  const r = call.result as { name?: string; mime_type?: string; web_view?: string; content?: string } | undefined;
  if (!r) return null;
  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line px-3.5 py-2">
        <a href={r.web_view} target="_blank" rel="noreferrer" className="text-[12.5px] font-medium text-ink hover:text-accent">
          {r.name}
        </a>
        <span className="chip">{labelMime(r.mime_type || "")}</span>
      </div>
      <pre className="max-h-[320px] overflow-auto whitespace-pre-wrap px-3.5 py-3 font-mono text-[12px] leading-5 text-ink">{r.content}</pre>
    </div>
  );
}

function DriveSummaryCard({ call }: { call: ToolCall }) {
  const r = call.result as { name?: string; mime_type?: string; web_view?: string; summary?: string } | undefined;
  if (!r) return null;
  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line px-3.5 py-2">
        <a href={r.web_view} target="_blank" rel="noreferrer" className="text-[12.5px] font-medium text-ink hover:text-accent">
          {r.name}
        </a>
        <span className="chip chip-accent">summary</span>
      </div>
      <div className="whitespace-pre-wrap px-3.5 py-3 text-[13px] leading-6 text-ink">{r.summary}</div>
    </div>
  );
}

function labelMime(mime: string) {
  if (mime === "application/vnd.google-apps.document") return "doc";
  if (mime === "application/vnd.google-apps.spreadsheet") return "sheet";
  if (mime === "application/vnd.google-apps.presentation") return "slides";
  if (mime === "application/vnd.google-apps.folder") return "folder";
  if (mime.startsWith("text/")) return mime.split("/")[1];
  if (mime.startsWith("application/")) return mime.split("/")[1].split(".").pop() || "file";
  return mime || "file";
}

// ─── actions ────────────────────────────────────────────────────────────

type ActionState = "pending" | "running" | "done" | "rejected" | "error";

function useApproval(actionId?: string) {
  const [state, setState] = useState<ActionState>("pending");
  const [result, setResult] = useState<unknown>(null);
  const [err, setErr] = useState("");

  async function decide(decision: "approved" | "rejected", edit_note?: string) {
    if (!actionId) return;
    setState(decision === "approved" ? "running" : "rejected");
    try {
      const res = await fetch(`/api/approvals/${actionId}/decide`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ decision: edit_note ? "edited" : decision, edit_note }),
      });
      const data = await res.json();
      if (decision === "rejected") return;
      if (data.executed && data.result?.ok) {
        setResult(data.result.result);
        setState("done");
      } else {
        setErr(data.result?.error || "execution failed");
        setState("error");
      }
    } catch (e) {
      setErr(String(e));
      setState("error");
    }
  }
  return { state, result, err, decide };
}

function ShellDraftCard({ call, actionId }: { call: ToolCall; actionId?: string }) {
  const r = call.result as {
    command?: string; reason?: string; safe_class?: boolean;
    first_token?: string; flags?: string[];
  } | undefined;
  const { state, result, err, decide } = useApproval(actionId);
  const out = (result as { stdout?: string; stderr?: string; exit_code?: number; truncated?: boolean }) ?? {};

  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line bg-warning/[0.05] px-3.5 py-2">
        <div className="flex items-center gap-2">
          <span className="chip chip-warn">Shell</span>
          <span className="text-[12px] text-ink-muted">{r?.first_token}</span>
          {r?.safe_class ? <span className="chip chip-ok">safe-class</span> : <span className="chip chip-warn">unfamiliar</span>}
          {(r?.flags ?? []).map((f) => <span key={f} className="chip chip-warn">{f}</span>)}
        </div>
        <span className="text-[11px] text-ink-subtle">
          {state === "done" ? `exit ${out.exit_code ?? "?"}` :
           state === "rejected" ? "rejected" :
           state === "running" ? "running…" :
           state === "error" ? "error" : "needs approval"}
        </span>
      </div>
      <div className="px-3.5 py-3">
        <pre className="overflow-x-auto rounded-[6px] border-l-2 border-warning bg-warning/[0.04] px-3 py-2.5 font-mono text-[12px] leading-6 text-ink">{r?.command}</pre>
        {r?.reason ? <div className="mt-2 text-[11.5px] text-ink-subtle">// {r.reason}</div> : null}
      </div>
      {state === "pending" ? (
        <div className="flex items-center gap-2 border-t border-line px-3.5 py-2.5">
          <button onClick={() => decide("approved")} className="btn btn-primary">Run it</button>
          <button onClick={() => decide("rejected")} className="btn btn-danger">Reject</button>
        </div>
      ) : null}
      {state === "done" ? (
        <div className="border-t border-line px-3.5 py-2.5">
          {out.stdout ? (
            <div>
              <div className="text-[10.5px] uppercase tracking-wider text-ink-subtle">stdout</div>
              <pre className="mt-1 overflow-x-auto rounded-[6px] bg-bg p-2.5 font-mono text-[11.5px] leading-5 text-ink">{out.stdout}</pre>
            </div>
          ) : null}
          {out.stderr ? (
            <div className="mt-2">
              <div className="text-[10.5px] uppercase tracking-wider text-danger">stderr</div>
              <pre className="mt-1 overflow-x-auto rounded-[6px] bg-danger/5 p-2.5 font-mono text-[11.5px] leading-5 text-danger">{out.stderr}</pre>
            </div>
          ) : null}
          {out.truncated ? <div className="mt-2 text-[10.5px] text-ink-subtle">output truncated.</div> : null}
        </div>
      ) : null}
      {state === "error" ? (
        <div className="border-t border-line px-3.5 py-2 text-[12px] text-danger">Error: {err}</div>
      ) : null}
    </div>
  );
}

function FileDraftCard({ call, actionId }: { call: ToolCall; actionId?: string }) {
  const r = call.result as { path?: string; append?: boolean; content?: string; bytes?: number } | undefined;
  const [body, setBody] = useState(r?.content ?? "");
  const [editing, setEditing] = useState(false);
  const { state, result, err, decide } = useApproval(actionId);
  const out = (result as { path?: string; bytes?: number }) ?? {};

  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line bg-warning/[0.05] px-3.5 py-2">
        <div className="flex items-center gap-2">
          <span className="chip chip-warn">{r?.append ? "Append" : "Write file"}</span>
          <span className="font-mono text-[12px] text-ink-muted">~/ro/scratch/{r?.path}</span>
        </div>
        <span className="text-[11px] text-ink-subtle">
          {state === "done" ? `wrote ${out.bytes ?? 0}B ✓` :
           state === "rejected" ? "rejected" :
           state === "running" ? "writing…" :
           state === "error" ? "error" : `${r?.bytes ?? 0}B pending`}
        </span>
      </div>
      <div className="px-3.5 py-3">
        {editing ? (
          <textarea value={body} onChange={(e) => setBody(e.target.value)}
            className="w-full min-h-[140px] resize-y rounded-[6px] border border-line bg-bg p-3 font-mono text-[12px] leading-6 text-ink outline-none focus:border-accent" />
        ) : (
          <pre className="overflow-x-auto rounded-[6px] border-l-2 border-warning bg-warning/[0.04] px-3 py-2.5 font-mono text-[12px] leading-6 text-ink">{body}</pre>
        )}
      </div>
      {state === "pending" ? (
        <div className="flex items-center gap-2 border-t border-line px-3.5 py-2.5">
          <button onClick={() => decide("approved", editing ? body : undefined)} className="btn btn-primary">
            {editing ? "Save & write" : "Write it"}
          </button>
          <button onClick={() => setEditing((v) => !v)} className="btn">{editing ? "Cancel edit" : "Edit"}</button>
          <button onClick={() => decide("rejected")} className="btn btn-danger">Reject</button>
        </div>
      ) : null}
      {state === "done" ? (
        <div className="border-t border-line px-3.5 py-2 text-[11.5px] text-ink-muted">wrote to <span className="font-mono">{out.path}</span></div>
      ) : null}
      {state === "error" ? (
        <div className="border-t border-line px-3.5 py-2 text-[12px] text-danger">Error: {err}</div>
      ) : null}
    </div>
  );
}

function BrowserDraftCard({ call, actionId }: { call: ToolCall; actionId?: string }) {
  const r = call.result as { url?: string } | undefined;
  const { state, result, err, decide } = useApproval(actionId);
  const out = (result as {
    final_url?: string; title?: string; text?: string; status?: number;
    screenshot_b64?: string; truncated?: boolean;
  }) ?? {};
  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line bg-warning/[0.05] px-3.5 py-2">
        <div className="flex items-center gap-2">
          <span className="chip chip-warn">Browser</span>
          <span className="font-mono text-[12px] text-ink-muted">{r?.url}</span>
        </div>
        <span className="text-[11px] text-ink-subtle">
          {state === "done" ? `${out.status ?? "?"} ✓` :
           state === "rejected" ? "rejected" :
           state === "running" ? "rendering…" :
           state === "error" ? "error" : "needs approval"}
        </span>
      </div>
      {state === "pending" ? (
        <div className="flex items-center gap-2 border-t border-line px-3.5 py-2.5">
          <button onClick={() => decide("approved")} className="btn btn-primary">Render</button>
          <button onClick={() => decide("rejected")} className="btn btn-danger">Reject</button>
        </div>
      ) : null}
      {state === "done" ? (
        <div className="border-t border-line">
          {out.title ? (
            <div className="px-3.5 py-2 text-[12.5px] font-medium text-ink">{out.title}</div>
          ) : null}
          {out.screenshot_b64 ? (
            <img
              src={`data:image/png;base64,${out.screenshot_b64}`}
              alt="page screenshot"
              className="block w-full border-y border-line"
            />
          ) : null}
          {out.text ? (
            <pre className="max-h-[280px] overflow-auto whitespace-pre-wrap px-3.5 py-3 text-[12px] leading-5 text-ink">{out.text}</pre>
          ) : null}
          {out.final_url && out.final_url !== r?.url ? (
            <div className="border-t border-line px-3.5 py-2 text-[11px] text-ink-subtle">
              redirected to <span className="font-mono">{out.final_url}</span>
            </div>
          ) : null}
        </div>
      ) : null}
      {state === "error" ? (
        <div className="border-t border-line px-3.5 py-2 text-[12px] text-danger">Error: {err}</div>
      ) : null}
    </div>
  );
}

function VisionDraftCard({ call, actionId }: { call: ToolCall; actionId?: string }) {
  const r = call.result as { source?: string; kind?: string; prompt?: string } | undefined;
  const { state, result, err, decide } = useApproval(actionId);
  const out = (result as { text?: string }) ?? {};
  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line bg-warning/[0.05] px-3.5 py-2">
        <div className="flex items-center gap-2">
          <span className="chip chip-warn">Vision</span>
          <span className="font-mono text-[12px] text-ink-muted">{r?.source}</span>
        </div>
        <span className="text-[11px] text-ink-subtle">
          {state === "done" ? "answered ✓" :
           state === "rejected" ? "rejected" :
           state === "running" ? "looking…" :
           state === "error" ? "error" : "needs approval"}
        </span>
      </div>
      <div className="px-3.5 py-3 text-[12.5px] text-ink-muted">
        <span className="text-ink-subtle">Asked:</span> <span className="text-ink">{r?.prompt}</span>
      </div>
      {state === "pending" ? (
        <div className="flex items-center gap-2 border-t border-line px-3.5 py-2.5">
          <button onClick={() => decide("approved")} className="btn btn-primary">Look</button>
          <button onClick={() => decide("rejected")} className="btn btn-danger">Reject</button>
        </div>
      ) : null}
      {state === "done" ? (
        <div className="border-t border-line px-3.5 py-3 text-[13px] leading-6 text-ink whitespace-pre-wrap">{out.text}</div>
      ) : null}
      {state === "error" ? (
        <div className="border-t border-line px-3.5 py-2 text-[12px] text-danger">Error: {err}</div>
      ) : null}
    </div>
  );
}

function BrowserStepCard({ call, actionId }: { call: ToolCall; actionId?: string }) {
  const r = call.result as {
    step?: string; url?: string; text?: string; label?: string; value?: string; pixels?: number;
  } | undefined;
  const { state, result, err, decide } = useApproval(actionId);
  const out = (result as {
    action?: string; final_url?: string; title?: string; text?: string;
    screenshot_b64?: string; elements?: { kind: string; label: string }[]; note?: string;
  }) ?? {};

  const stepLabel = (() => {
    if (!r) return "browser step";
    if (r.step === "goto") return `Open ${r.url}`;
    if (r.step === "click") return `Click "${r.text}"`;
    if (r.step === "fill") return `Fill "${r.label}" = "${r.value}"`;
    if (r.step === "scroll") return `Scroll ${r.pixels}px`;
    if (r.step === "close") return "Close session";
    return r.step || "step";
  })();

  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line bg-warning/[0.05] px-3.5 py-2">
        <div className="flex items-center gap-2">
          <span className="chip chip-warn">Browser {r?.step}</span>
          <span className="text-[12px] text-ink-muted">{stepLabel}</span>
        </div>
        <span className="text-[11px] text-ink-subtle">
          {state === "done" ? "done ✓" :
           state === "rejected" ? "rejected" :
           state === "running" ? "running…" :
           state === "error" ? "error" : "needs approval"}
        </span>
      </div>
      {state === "pending" ? (
        <div className="flex items-center gap-2 border-t border-line px-3.5 py-2.5">
          <button onClick={() => decide("approved")} className="btn btn-primary">Run step</button>
          <button onClick={() => decide("rejected")} className="btn btn-danger">Skip</button>
        </div>
      ) : null}
      {state === "done" ? (
        <div className="border-t border-line">
          {out.title ? (
            <div className="px-3.5 py-2 text-[12.5px] font-medium text-ink">{out.title}</div>
          ) : null}
          {out.screenshot_b64 ? (
            <img
              src={`data:image/png;base64,${out.screenshot_b64}`}
              alt="page after step"
              className="block w-full border-y border-line"
            />
          ) : null}
          {out.elements && out.elements.length ? (
            <div className="border-t border-line px-3.5 py-2">
              <div className="mb-1 text-[10.5px] uppercase tracking-wider text-ink-subtle">visible targets</div>
              <div className="flex flex-wrap gap-1">
                {out.elements.slice(0, 16).map((el, i) => (
                  <span key={i} className="chip" title={el.kind}>{el.label}</span>
                ))}
              </div>
            </div>
          ) : null}
          {out.note ? (
            <div className="border-t border-line px-3.5 py-2 text-[11px] text-warning">{out.note}</div>
          ) : null}
        </div>
      ) : null}
      {state === "error" ? (
        <div className="border-t border-line px-3.5 py-2 text-[12px] text-danger">Error: {err}</div>
      ) : null}
    </div>
  );
}

function WebDraftCard({ call, actionId }: { call: ToolCall; actionId?: string }) {
  const r = call.result as { url?: string; method?: string } | undefined;
  const { state, result, err, decide } = useApproval(actionId);
  const out = (result as { status?: number; url?: string; body?: string; truncated?: boolean }) ?? {};

  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line bg-warning/[0.05] px-3.5 py-2">
        <div className="flex items-center gap-2">
          <span className="chip chip-warn">Web</span>
          <span className="font-mono text-[12px] text-ink-muted">{r?.method} {r?.url}</span>
        </div>
        <span className="text-[11px] text-ink-subtle">
          {state === "done" ? `${out.status ?? "?"} ✓` :
           state === "rejected" ? "rejected" :
           state === "running" ? "fetching…" :
           state === "error" ? "error" : "needs approval"}
        </span>
      </div>
      {state === "pending" ? (
        <div className="flex items-center gap-2 border-t border-line px-3.5 py-2.5">
          <button onClick={() => decide("approved")} className="btn btn-primary">Fetch</button>
          <button onClick={() => decide("rejected")} className="btn btn-danger">Reject</button>
        </div>
      ) : null}
      {state === "done" && out.body ? (
        <div className="border-t border-line px-3.5 py-2.5">
          <pre className="max-h-[280px] overflow-auto rounded-[6px] bg-bg p-2.5 font-mono text-[11.5px] leading-5 text-ink">{out.body}</pre>
          {out.truncated ? <div className="mt-1 text-[10.5px] text-ink-subtle">response truncated.</div> : null}
        </div>
      ) : null}
      {state === "error" ? (
        <div className="border-t border-line px-3.5 py-2 text-[12px] text-danger">Error: {err}</div>
      ) : null}
    </div>
  );
}

// ─── imessage ───────────────────────────────────────────────────────────

function IMessageHistoryCard({ call }: { call: ToolCall }) {
  const r = call.result as { with?: string; messages?: { from: string; text: string; at: string }[] } | undefined;
  const msgs = r?.messages ?? [];
  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="border-b border-line px-3.5 py-2 text-[12px] font-medium text-ink">
        iMessage · {r?.with}
      </div>
      <ul>
        {msgs.map((m, i) => (
          <li key={i} className="border-b border-line px-3.5 py-2 last:border-b-0">
            <div className="flex items-baseline justify-between">
              <span className="text-[11.5px] font-medium text-ink-muted">{m.from}</span>
              <span className="text-[10.5px] text-ink-subtle">{shortDate(m.at)}</span>
            </div>
            <div className="mt-0.5 text-[12.5px] text-ink">{m.text}</div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function IMessageThreadsCard({ call }: { call: ToolCall }) {
  type T = { name: string; last: string; from_me: boolean; at: string };
  const ts = (Array.isArray(call.result) ? call.result : []) as T[];
  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="border-b border-line px-3.5 py-2 text-[12px] font-medium text-ink">
        iMessage · recent threads
      </div>
      <ul>
        {ts.map((t, i) => (
          <li key={i} className="border-b border-line px-3.5 py-2 last:border-b-0">
            <div className="flex items-baseline justify-between">
              <span className="text-[13px] font-medium text-ink">{t.name}</span>
              <span className="text-[10.5px] text-ink-subtle">{shortDate(t.at)}</span>
            </div>
            <div className="mt-0.5 line-clamp-1 text-[12px] text-ink-muted">
              <span className="text-ink-subtle">{t.from_me ? "you: " : ""}</span>{t.last}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function WhatsAppDraftCard({ call, actionId }: { call: ToolCall; actionId?: string }) {
  const r = call.result as { to?: string; to_name?: string; body?: string } | undefined;
  const [body, setBody] = useState(r?.body ?? "");
  const [editing, setEditing] = useState(false);
  const { state, result, err, decide } = useApproval(actionId);
  const out = (result as { sid?: string; status?: string }) ?? {};
  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line bg-warning/[0.05] px-3.5 py-2">
        <div className="flex items-center gap-2">
          <span className="chip chip-warn">WhatsApp</span>
          <span className="font-mono text-[12px] text-ink-muted">{r?.to_name || r?.to}</span>
        </div>
        <span className="text-[11px] text-ink-subtle">
          {state === "done" ? `${out.status ?? "sent"} ✓` :
           state === "rejected" ? "rejected" :
           state === "running" ? "sending…" :
           state === "error" ? "error" : "needs approval"}
        </span>
      </div>
      <div className="px-3.5 py-3">
        {editing ? (
          <textarea value={body} onChange={(e) => setBody(e.target.value)}
            className="w-full min-h-[100px] resize-y rounded-[6px] border border-line bg-bg p-3 text-[13px] leading-6 text-ink outline-none focus:border-accent" />
        ) : (
          <div className="whitespace-pre-wrap rounded-[6px] border-l-2 border-warning bg-warning/[0.04] px-3 py-2.5 text-[13px] leading-6 text-ink">{body}</div>
        )}
      </div>
      {state === "pending" ? (
        <div className="flex items-center gap-2 border-t border-line px-3.5 py-2.5">
          <button onClick={() => decide("approved", editing ? body : undefined)} className="btn btn-primary">
            {editing ? "Save & send" : "Send"}
          </button>
          <button onClick={() => setEditing((v) => !v)} className="btn">{editing ? "Cancel edit" : "Edit"}</button>
          <button onClick={() => decide("rejected")} className="btn btn-danger">Reject</button>
        </div>
      ) : null}
      {state === "error" ? (
        <div className="border-t border-line px-3.5 py-2 text-[12px] text-danger">Error: {err}</div>
      ) : null}
    </div>
  );
}

function TelegramDraftCard({ call, actionId }: { call: ToolCall; actionId?: string }) {
  const r = call.result as { chat_id?: number | string; to_name?: string; body?: string } | undefined;
  const [body, setBody] = useState(r?.body ?? "");
  const [editing, setEditing] = useState(false);
  const { state, result, err, decide } = useApproval(actionId);
  const out = (result as { chat_id?: number | string; message_id?: number }) ?? {};
  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line bg-warning/[0.05] px-3.5 py-2">
        <div className="flex items-center gap-2">
          <span className="chip chip-warn">Telegram</span>
          <span className="text-[12px] text-ink-muted">to {r?.to_name || r?.chat_id}</span>
        </div>
        <span className="text-[11px] text-ink-subtle">
          {state === "done" ? "sent ✓" :
           state === "rejected" ? "rejected" :
           state === "running" ? "sending…" :
           state === "error" ? "error" : "needs approval"}
        </span>
      </div>
      <div className="px-3.5 py-3">
        {editing ? (
          <textarea value={body} onChange={(e) => setBody(e.target.value)}
            className="w-full min-h-[100px] resize-y rounded-[6px] border border-line bg-bg p-3 text-[13px] leading-6 text-ink outline-none focus:border-accent" />
        ) : (
          <div className="whitespace-pre-wrap rounded-[6px] border-l-2 border-warning bg-warning/[0.04] px-3 py-2.5 text-[13px] leading-6 text-ink">{body}</div>
        )}
      </div>
      {state === "pending" ? (
        <div className="flex items-center gap-2 border-t border-line px-3.5 py-2.5">
          <button onClick={() => decide("approved", editing ? body : undefined)} className="btn btn-primary">
            {editing ? "Save & send" : "Send"}
          </button>
          <button onClick={() => setEditing((v) => !v)} className="btn">{editing ? "Cancel edit" : "Edit"}</button>
          <button onClick={() => decide("rejected")} className="btn btn-danger">Reject</button>
        </div>
      ) : null}
      {state === "error" ? (
        <div className="border-t border-line px-3.5 py-2 text-[12px] text-danger">Error: {err}</div>
      ) : null}
    </div>
  );
}

function IMessageDraftCard({ call, actionId }: { call: ToolCall; actionId?: string }) {
  const r = call.result as { recipient?: string; body?: string } | undefined;
  const [body, setBody] = useState(r?.body ?? "");
  const [editing, setEditing] = useState(false);
  const [state, setState] = useState<"pending" | "sent" | "rejected" | "sending" | "error">("pending");
  const [err, setErr] = useState("");

  async function decide(decision: "approved" | "rejected" | "edited") {
    if (!actionId) return;
    setState("sending");
    try {
      const res = await fetch(`/api/approvals/${actionId}/decide`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          decision,
          edit_note: decision === "edited" ? body : undefined,
        }),
      });
      const data = await res.json();
      if (decision === "rejected") setState("rejected");
      else if (data.executed && data.result?.ok) setState("sent");
      else { setState("error"); setErr(data.result?.error || "send failed"); }
    } catch (e) {
      setState("error");
      setErr(String(e));
    }
  }

  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line bg-warning/[0.05] px-3.5 py-2">
        <div className="flex items-center gap-2">
          <span className="chip chip-warn">iMessage draft</span>
          <span className="text-[12px] text-ink-muted">to {r?.recipient}</span>
        </div>
        <span className="text-[11px] text-ink-subtle">
          {state === "sent" ? "sent ✓" : state === "rejected" ? "rejected" : state === "sending" ? "sending…" : "needs approval"}
        </span>
      </div>
      <div className="px-3.5 py-3">
        {editing ? (
          <textarea value={body} onChange={(e) => setBody(e.target.value)}
            className="w-full min-h-[100px] resize-y rounded-[6px] border border-line bg-bg p-3 text-[13px] leading-6 text-ink outline-none focus:border-accent" />
        ) : (
          <div className="whitespace-pre-wrap rounded-[6px] border-l-2 border-warning bg-warning/[0.04] px-3 py-2.5 text-[13px] leading-6 text-ink">{body}</div>
        )}
      </div>
      {state === "pending" ? (
        <div className="flex items-center gap-2 border-t border-line px-3.5 py-2.5">
          <button onClick={() => decide(editing ? "edited" : "approved")} className="btn btn-primary">
            {editing ? "Save & send" : "Send"}
          </button>
          <button onClick={() => setEditing((v) => !v)} className="btn">{editing ? "Cancel edit" : "Edit"}</button>
          <button onClick={() => decide("rejected")} className="btn btn-danger">Reject</button>
        </div>
      ) : null}
      {state === "error" ? (
        <div className="border-t border-line px-3.5 py-2 text-[12px] text-danger">Error: {err}</div>
      ) : null}
    </div>
  );
}

// ─── slack ──────────────────────────────────────────────────────────────

function SlackHistoryCard({ call }: { call: ToolCall }) {
  const r = call.result as { with?: string; messages?: { ts: string; user: string; text: string }[] } | undefined;
  const msgs = r?.messages ?? [];
  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line px-3.5 py-2">
        <div className="text-[12px] font-medium text-ink">Slack · DM with {r?.with}</div>
        <span className="text-[11px] text-ink-subtle">{msgs.length} messages</span>
      </div>
      <ul>
        {msgs.map((m, i) => (
          <li key={i} className="border-b border-line px-3.5 py-2 last:border-b-0">
            <div className="text-[11.5px] font-medium text-ink-muted">{m.user}</div>
            <div className="mt-0.5 whitespace-pre-wrap text-[12.5px] text-ink">{m.text}</div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function SlackSearchCard({ call }: { call: ToolCall }) {
  type Hit = { channel: string; user: string; text: string; permalink?: string };
  const hits = (Array.isArray(call.result) ? call.result : []) as Hit[];
  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line px-3.5 py-2">
        <div className="text-[12px] font-medium text-ink">Slack · search</div>
        <span className="text-[11px] text-ink-subtle">
          {(call.args as { query?: string } | undefined)?.query}
        </span>
      </div>
      <ul>
        {hits.map((h, i) => (
          <li key={i} className="border-b border-line px-3.5 py-2 last:border-b-0">
            <div className="text-[11.5px] text-ink-muted">#{h.channel} · {h.user}</div>
            <a href={h.permalink} target="_blank" rel="noreferrer" className="mt-0.5 block text-[12.5px] text-ink hover:text-accent">
              {h.text}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}

function SlackDmsCard({ call }: { call: ToolCall }) {
  type DM = { name: string; channel_id: string };
  const dms = (Array.isArray(call.result) ? call.result : []) as DM[];
  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="border-b border-line px-3.5 py-2 text-[12px] font-medium text-ink">Slack · recent DMs</div>
      <ul>
        {dms.map((d) => (
          <li key={d.channel_id} className="border-b border-line px-3.5 py-2 last:border-b-0 text-[13px] text-ink hover:bg-surface-hover">
            {d.name}
          </li>
        ))}
      </ul>
    </div>
  );
}

function SlackDraftCard({ call, actionId }: { call: ToolCall; actionId?: string }) {
  const r = call.result as {
    channel_name?: string;
    is_dm?: boolean;
    body?: string;
  } | undefined;
  const [body, setBody] = useState(r?.body ?? "");
  const [editing, setEditing] = useState(false);
  const [state, setState] = useState<"pending" | "sent" | "rejected" | "sending" | "error">("pending");
  const [err, setErr] = useState("");

  async function decide(decision: "approved" | "rejected" | "edited") {
    if (!actionId) return;
    setState("sending");
    try {
      const res = await fetch(`/api/approvals/${actionId}/decide`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          decision,
          edit_note: decision === "edited" ? body : undefined,
        }),
      });
      const data = await res.json();
      if (decision === "rejected") setState("rejected");
      else if (data.executed && data.result?.ok) setState("sent");
      else { setState("error"); setErr(data.result?.error || "send failed"); }
    } catch (e) {
      setState("error");
      setErr(String(e));
    }
  }

  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line bg-warning/[0.05] px-3.5 py-2">
        <div className="flex items-center gap-2">
          <span className="chip chip-warn">Slack draft</span>
          <span className="text-[12px] text-ink-muted">
            {r?.is_dm ? `DM to ${r.channel_name}` : `Post to ${r?.channel_name}`}
          </span>
        </div>
        <span className="text-[11px] text-ink-subtle">
          {state === "sent" ? "sent ✓" : state === "rejected" ? "rejected" : state === "sending" ? "sending…" : "needs approval"}
        </span>
      </div>
      <div className="px-3.5 py-3">
        {editing ? (
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            className="w-full min-h-[120px] resize-y rounded-[6px] border border-line bg-bg p-3 text-[13px] leading-6 text-ink outline-none focus:border-accent"
          />
        ) : (
          <div className="whitespace-pre-wrap rounded-[6px] border-l-2 border-warning bg-warning/[0.04] px-3 py-2.5 text-[13px] leading-6 text-ink">
            {body}
          </div>
        )}
      </div>
      {state === "pending" ? (
        <div className="flex items-center gap-2 border-t border-line px-3.5 py-2.5">
          <button onClick={() => decide(editing ? "edited" : "approved")} className="btn btn-primary">
            {editing ? "Save & send" : "Send"}
          </button>
          <button onClick={() => setEditing((v) => !v)} className="btn">
            {editing ? "Cancel edit" : "Edit"}
          </button>
          <button onClick={() => decide("rejected")} className="btn btn-danger">Reject</button>
        </div>
      ) : null}
      {state === "error" ? (
        <div className="border-t border-line px-3.5 py-2 text-[12px] text-danger">Error: {err}</div>
      ) : null}
    </div>
  );
}

// ─── calendar ──────────────────────────────────────────────────────────

function CalendarEventsCard({ call }: { call: ToolCall }) {
  type Ev = {
    event_id: string;
    title: string;
    start: string;
    end: string;
    location?: string;
    attendees?: string[];
    hangout_link?: string;
    all_day?: boolean;
  };
  const events = (
    Array.isArray(call.result) ? (call.result as Ev[]) :
    call.result && typeof call.result === "object" ? [call.result as Ev] :
    []
  );

  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line px-3.5 py-2">
        <div className="flex items-center gap-2 text-[12px]">
          <span className="font-medium text-ink">Calendar</span>
          <span className="text-ink-muted">·</span>
          <span className="text-ink-muted">{events.length} event{events.length === 1 ? "" : "s"}</span>
        </div>
      </div>
      <ul>
        {events.map((e) => (
          <li key={e.event_id} className="border-b border-line px-3.5 py-2.5 last:border-b-0 hover:bg-surface-hover">
            <div className="flex items-baseline gap-2">
              <span className="text-[12px] font-medium text-accent">{fmtEventTime(e.start, e.all_day)}</span>
              {e.hangout_link ? <span className="chip chip-accent">Meet</span> : null}
            </div>
            <div className="mt-0.5 text-[13px] text-ink">{e.title}</div>
            {e.attendees && e.attendees.length ? (
              <div className="mt-0.5 truncate text-[11.5px] text-ink-subtle">
                {e.attendees.slice(0, 4).join(", ")}{e.attendees.length > 4 ? ` +${e.attendees.length - 4}` : ""}
              </div>
            ) : null}
            {e.location ? <div className="text-[11.5px] text-ink-subtle">📍 {e.location}</div> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

function FreeSlotsCard({ call }: { call: ToolCall }) {
  type Slot = { start: string; end: string; duration_min: number };
  const slots = (Array.isArray(call.result) ? call.result : []) as Slot[];

  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line px-3.5 py-2">
        <div className="text-[12px] font-medium text-ink">Open slots</div>
        <span className="text-[11px] text-ink-subtle">
          {(call.args as { duration_min?: number } | undefined)?.duration_min ?? ""} min
        </span>
      </div>
      <ul>
        {slots.map((s, i) => (
          <li key={i} className="flex items-center justify-between border-b border-line px-3.5 py-2 last:border-b-0 hover:bg-surface-hover">
            <div className="text-[12.5px] text-ink">{fmtSlot(s.start, s.end)}</div>
            <button className="btn btn-ghost px-2 py-0.5 text-[11px]">Pick</button>
          </li>
        ))}
        {!slots.length ? <li className="px-4 py-3 text-[12px] text-ink-subtle">No open slots.</li> : null}
      </ul>
    </div>
  );
}

function CalendarDraftCard({ call, actionId }: { call: ToolCall; actionId?: string }) {
  const r = call.result as {
    title?: string;
    start?: string;
    end?: string;
    duration_min?: number;
    attendees?: string[];
    with_meet_link?: boolean;
  } | undefined;
  const [state, setState] = useState<"pending" | "booked" | "rejected" | "sending" | "error">("pending");
  const [err, setErr] = useState("");

  async function decide(decision: "approved" | "rejected") {
    if (!actionId) return;
    setState("sending");
    try {
      const res = await fetch(`/api/approvals/${actionId}/decide`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ decision }),
      });
      const data = await res.json();
      if (decision === "rejected") setState("rejected");
      else if (data.executed && data.result?.ok) setState("booked");
      else { setState("error"); setErr(data.result?.error || "book failed"); }
    } catch (e) {
      setState("error");
      setErr(String(e));
    }
  }

  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line bg-warning/[0.05] px-3.5 py-2">
        <div className="flex items-center gap-2">
          <span className="chip chip-warn">New event</span>
          <span className="text-[12px] text-ink-muted">{r?.title}</span>
        </div>
        <span className="text-[11px] text-ink-subtle">
          {state === "booked" ? "booked ✓" :
           state === "rejected" ? "rejected" :
           state === "sending" ? "booking…" : "needs approval"}
        </span>
      </div>
      <div className="px-3.5 py-3 text-[12.5px]">
        <div className="text-ink-muted"><span className="text-ink-subtle">When:</span> {fmtSlot(r?.start ?? "", r?.end ?? "")}</div>
        {r?.attendees?.length ? (
          <div className="mt-1 text-ink-muted"><span className="text-ink-subtle">With:</span> {r.attendees.join(", ")}</div>
        ) : null}
        {r?.with_meet_link ? <div className="mt-1 text-ink-muted">Will include a Google Meet link.</div> : null}
      </div>
      {state === "pending" ? (
        <div className="flex items-center gap-2 border-t border-line px-3.5 py-2.5">
          <button onClick={() => decide("approved")} className="btn btn-primary">Book it</button>
          <button onClick={() => decide("rejected")} className="btn btn-danger">Cancel</button>
        </div>
      ) : null}
      {state === "error" ? (
        <div className="border-t border-line px-3.5 py-2 text-[12px] text-danger">Error: {err}</div>
      ) : null}
    </div>
  );
}

// ─── github ─────────────────────────────────────────────────────────────

function GithubReposCard({ call }: { call: ToolCall }) {
  type Repo = {
    full_name: string;
    description: string;
    private: boolean;
    pushed_at: string;
    language: string;
    open_issues: number;
    html_url: string;
  };
  const repos = (Array.isArray(call.result) ? call.result : []) as Repo[];
  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line px-3.5 py-2">
        <div className="text-[12px] font-medium text-ink">GitHub · repos</div>
      </div>
      <ul>
        {repos.map((r) => (
          <li key={r.full_name} className="border-b border-line px-3.5 py-2.5 last:border-b-0 hover:bg-surface-hover">
            <div className="flex items-baseline justify-between gap-2">
              <a href={r.html_url} target="_blank" rel="noreferrer" className="truncate text-[13px] font-medium text-ink hover:text-accent">
                {r.full_name}
              </a>
              <div className="flex shrink-0 items-center gap-1.5">
                {r.language ? <span className="chip">{r.language}</span> : null}
                {r.private ? <span className="chip chip-warn">private</span> : null}
              </div>
            </div>
            {r.description ? <div className="mt-0.5 line-clamp-1 text-[12px] text-ink-muted">{r.description}</div> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

function GithubPRsCard({ call }: { call: ToolCall }) {
  type Pr = { number: number; repo: string; title: string; author: string; draft: boolean; url: string };
  const prs = (Array.isArray(call.result) ? call.result : []) as Pr[];
  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line px-3.5 py-2">
        <div className="text-[12px] font-medium text-ink">GitHub · open PRs</div>
      </div>
      <ul>
        {prs.map((p) => (
          <li key={`${p.repo}-${p.number}`} className="flex items-start gap-2 border-b border-line px-3.5 py-2 last:border-b-0 hover:bg-surface-hover">
            <span className="mt-0.5 font-mono text-[11px] text-ink-subtle">#{p.number}</span>
            <div className="min-w-0 flex-1">
              <a href={p.url} target="_blank" rel="noreferrer" className="text-[13px] text-ink hover:text-accent">{p.title}</a>
              <div className="text-[11.5px] text-ink-subtle">{p.repo} · by {p.author}{p.draft ? " · draft" : ""}</div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function GithubCommitsCard({ call }: { call: ToolCall }) {
  type C = { short_sha: string; author: string; message: string; url: string; committed_at: string };
  const commits = (Array.isArray(call.result) ? call.result : []) as C[];
  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line px-3.5 py-2">
        <div className="text-[12px] font-medium text-ink">Recent commits</div>
      </div>
      <ul>
        {commits.map((c) => (
          <li key={c.short_sha} className="flex items-start gap-3 border-b border-line px-3.5 py-2 last:border-b-0 font-mono text-[12px]">
            <a href={c.url} target="_blank" rel="noreferrer" className="text-accent">{c.short_sha}</a>
            <div className="min-w-0 flex-1">
              <div className="truncate text-ink">{c.message}</div>
              <div className="text-[11px] text-ink-subtle">{c.author} · {shortDate(c.committed_at)}</div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function GithubSummaryCard({ call }: { call: ToolCall }) {
  const r = call.result as {
    repo?: string;
    description?: string;
    open_prs?: number;
    open_issues?: number;
    language?: string;
    pushed_at?: string;
    recent_commits?: { short_sha: string; author: string; message: string; at: string }[];
  } | undefined;
  if (!r) return null;
  return (
    <div className="rounded-[10px] border border-line bg-surface p-3.5">
      <div className="flex items-baseline justify-between">
        <div className="text-[13px] font-semibold text-ink">{r.repo}</div>
        <div className="flex gap-1.5">
          <span className="chip">{r.open_prs ?? 0} PRs</span>
          <span className="chip">{r.open_issues ?? 0} issues</span>
          {r.language ? <span className="chip">{r.language}</span> : null}
        </div>
      </div>
      {r.description ? <div className="mt-1 text-[12.5px] text-ink-muted">{r.description}</div> : null}
      {r.recent_commits && r.recent_commits.length ? (
        <ul className="mt-3 space-y-1 font-mono text-[11.5px]">
          {r.recent_commits.slice(0, 5).map((c) => (
            <li key={c.short_sha} className="flex gap-2">
              <span className="text-accent">{c.short_sha}</span>
              <span className="truncate text-ink">{c.message}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

// ─── helpers ────────────────────────────────────────────────────────────

function fmtEventTime(iso: string, allDay?: boolean) {
  if (!iso) return "";
  try {
    if (allDay) {
      const d = new Date(iso);
      return d.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" }) + " (all day)";
    }
    const d = new Date(iso);
    return d.toLocaleString([], { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  } catch {
    return iso;
  }
}

function fmtSlot(start: string, end: string) {
  if (!start) return "";
  try {
    const s = new Date(start);
    const e = end ? new Date(end) : null;
    const dayPart = s.toLocaleString([], { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
    if (!e) return dayPart;
    return `${dayPart} – ${e.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`;
  } catch {
    return `${start} – ${end}`;
  }
}

function GmailListCard({ call }: { call: ToolCall }) {
  type Thread = {
    thread_id: string;
    from_name: string;
    from_email: string;
    subject: string;
    snippet: string;
    received_at: string;
    unread: boolean;
  };
  const threads = (Array.isArray(call.result) ? call.result : []) as Thread[];

  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line px-3.5 py-2">
        <div className="flex items-center gap-2 text-[12px] text-ink-muted">
          <span className="font-medium text-ink">Gmail</span>
          <span>·</span>
          <span>{threads.length} thread{threads.length === 1 ? "" : "s"}</span>
        </div>
        <span className="text-[11px] text-ink-subtle">
          {(call.args as { query?: string } | undefined)?.query || ""}
        </span>
      </div>
      <ul>
        {threads.map((t) => (
          <li
            key={t.thread_id}
            className="flex items-start gap-3 border-b border-line px-3.5 py-2.5 last:border-b-0 hover:bg-surface-hover"
          >
            <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent-soft text-[10.5px] font-semibold text-accent">
              {initials(t.from_name || t.from_email)}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-baseline gap-2">
                <span className="text-[13px] font-medium text-ink">{t.from_name || t.from_email}</span>
                {t.unread ? <span className="h-1.5 w-1.5 rounded-full bg-accent" /> : null}
                <span className="ml-auto text-[11px] text-ink-subtle">{shortDate(t.received_at)}</span>
              </div>
              <div className="mt-0.5 truncate text-[12.5px] text-ink-muted">{t.subject}</div>
              <div className="mt-0.5 line-clamp-1 text-[12px] text-ink-subtle">{t.snippet}</div>
            </div>
          </li>
        ))}
        {!threads.length ? <li className="px-4 py-3 text-[12px] text-ink-subtle">No results.</li> : null}
      </ul>
    </div>
  );
}

function GmailDraftCard({ call, actionId }: { call: ToolCall; actionId?: string }) {
  const r = call.result as
    | { draft_id?: string; to?: string; from_name?: string; subject?: string; body?: string }
    | undefined;
  const [body, setBody] = useState(r?.body ?? "");
  const [editing, setEditing] = useState(false);
  const [state, setState] = useState<"pending" | "sent" | "rejected" | "sending" | "error">("pending");
  const [err, setErr] = useState("");

  async function decide(decision: "approved" | "rejected" | "edited") {
    if (!actionId) return;
    setState("sending");
    try {
      const r = await fetch(`/api/approvals/${actionId}/decide`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          decision,
          edit_note: decision === "edited" ? body : undefined,
        }),
      });
      const data = await r.json();
      if (decision === "rejected") setState("rejected");
      else if (data.executed && data.result?.ok) setState("sent");
      else { setState("error"); setErr(data.result?.error || "send failed"); }
    } catch (e) {
      setState("error");
      setErr(String(e));
    }
  }

  return (
    <div className="rounded-[10px] border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line bg-warning/[0.05] px-3.5 py-2">
        <div className="flex items-center gap-2 text-[12px]">
          <span className="chip chip-warn">Draft</span>
          <span className="text-ink-muted">
            To {r?.from_name || r?.to || "recipient"}
          </span>
        </div>
        <span className="text-[11px] text-ink-subtle">
          {state === "sent" ? "sent ✓" : state === "rejected" ? "rejected" : state === "sending" ? "sending…" : "needs approval"}
        </span>
      </div>
      <div className="px-3.5 py-3 text-[12.5px]">
        <div className="mb-1.5 text-ink-muted">
          <span className="text-ink-subtle">Subject:</span> <span className="text-ink">{r?.subject}</span>
        </div>
        {editing ? (
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            className="w-full min-h-[160px] resize-y rounded-[6px] border border-line bg-bg p-3 text-[13px] leading-6 text-ink outline-none focus:border-accent"
          />
        ) : (
          <div className="whitespace-pre-wrap rounded-[6px] border-l-2 border-warning bg-warning/[0.04] px-3 py-2.5 text-[13px] leading-6 text-ink">
            {body}
          </div>
        )}
      </div>
      {state === "pending" ? (
        <div className="flex items-center gap-2 border-t border-line px-3.5 py-2.5">
          <button
            onClick={() => decide(editing ? "edited" : "approved")}
            className="btn btn-primary"
          >
            {editing ? "Save & send" : "Approve & send"}
          </button>
          <button onClick={() => setEditing((v) => !v)} className="btn">
            {editing ? "Cancel edit" : "Edit"}
          </button>
          <button onClick={() => decide("rejected")} className="btn btn-danger">
            Reject
          </button>
        </div>
      ) : null}
      {state === "error" ? (
        <div className="border-t border-line px-3.5 py-2 text-[12px] text-danger">Error: {err}</div>
      ) : null}
    </div>
  );
}

function StatsPill() {
  const [data, setData] = useState<{
    total: number; approved: number; edited: number; rejected: number;
    approve_rate: number;
  } | null>(null);

  useEffect(() => {
    fetch("/api/eval/stats?days=7")
      .then((r) => r.json())
      .then(setData)
      .catch(() => setData(null));
  }, []);

  if (!data || data.total === 0) return null;
  return (
    <div className="mx-auto mt-6 flex max-w-fit items-center gap-2 rounded-full border border-line bg-surface px-3 py-1.5 text-[11.5px] text-ink-muted">
      <span className="font-medium text-ink">last 7 days</span>
      <span className="text-ink-subtle">·</span>
      <span>{data.approved} approved</span>
      {data.edited > 0 ? <><span className="text-ink-subtle">·</span><span>{data.edited} edited</span></> : null}
      {data.rejected > 0 ? <><span className="text-ink-subtle">·</span><span>{data.rejected} rejected</span></> : null}
      <span className="text-ink-subtle">·</span>
      <span className="text-success">{Math.round(data.approve_rate * 100)}% approve rate</span>
    </div>
  );
}

function StreamingIndicator({ stage }: { stage: string }) {
  return (
    <div className="flex gap-3">
      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-[7px] bg-accent text-[11px] font-semibold text-accent-ink">
        r
      </div>
      <div className="flex items-center gap-2 text-[13px] text-ink-muted">
        <span className="flex gap-1">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ink-subtle" style={{ animationDelay: "0ms" }} />
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ink-subtle" style={{ animationDelay: "200ms" }} />
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ink-subtle" style={{ animationDelay: "400ms" }} />
        </span>
        <span>{stage || "thinking"}…</span>
      </div>
    </div>
  );
}

function initials(name: string) {
  return (name || "?")
    .split(/[\s@.]+/)
    .map((s) => s[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

function shortDate(iso: string) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const today = new Date();
    if (d.toDateString() === today.toDateString())
      return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    return d.toLocaleDateString([], { month: "short", day: "numeric" });
  } catch {
    return "";
  }
}
