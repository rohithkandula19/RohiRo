# decisions

a running log of choices made building ro. each entry is a date, the choice, and the reason. when something changes, add a new entry, don't edit history.

## 2026-05-01 phase 0 starts

- monorepo with turborepo + pnpm. why: shared types between web and api, single install, parallel dev, future-proof if more apps land.
- next.js 14 app router. why: rsc + streaming for sse traces, file-based routes match the "every domain a page" model, pwa works.
- fastapi over flask or starlette. why: openapi out of the box gives us auto-typed clients in `packages/types`, async first.
- langgraph for supervisor and sub-agents. why: explicit graph state, durable interrupts for human approval, traces drop into langfuse cleanly.
- postgres 16 + pgvector + redis. why: pgvector keeps memory hybrid retrieval in one db, redis handles ephemeral session state and pubsub for sse.
- claude sonnet 4.6 default in code (not 4.5 as in spec). why: 4.6 is the latest sonnet generation per current model lineup. 4.5 retired. opus 4.7 for hard reasoning, haiku 4.5 for classifier. logged as override.
- shadcn copied in and restyled rather than depended on. why: spec says heavy restyle, shadcn cli copies anyway, owning the source means we can keep the editorial style consistent.
- monaco for the profile editor. why: spec asks for live save with markdown syntax. monaco handles that well and ships in a single dynamic import.
- openai text-embedding-3-small for embeddings. why: cheap, fast, 1536 dim works well with pgvector ivfflat. swappable behind a wrapper.
- keychain via `keyring` (python). why: spec is explicit. one library for both setup script and runtime.
- whisper local for voice. why: spec is explicit, keeps audio off the network, mac silicon is fast enough.
- secrets handling: every tool reads from `keyring.get_password("ro", "<name>")` at startup, fails loudly with a clear todo if missing. no fallback to env.
- writing style: enforced everywhere. no em dashes. sentence case. short sentences. these decisions docs follow the same rules.
- single claude client wrapper at `api/observability/claude.py`. why: retries, token logging, model fallback, langfuse spans live in one place.
- repository pattern in `api/memory/repos/`. agents never write raw sql.
- approvals pause the langgraph state via `interrupt_before` on the approval node. resume via the api after the user says yes/no/edit.
- model defaults are also overridable per request in the supervisor input. why: settings page can switch them without restart.

## 2026-05-01 phase 1 done

- supervisor pipeline live: intake → memory inject → classify → dispatch → synthesize → log.
- /api/chat returns a single response. /api/chat/stream emits sse events the command palette consumes.
- /overview hero + live trace card render. live trace listens on /api/trace/stream and falls back to a static example until the first real event.
- all 12 routes (overview through settings) exist with editorial design system. each has a kicker + serif headline + cards.
- command palette (cmd-k) opens globally. it routes to pages on a "go to ..." match, otherwise streams chat through the supervisor.
- sub-agent dispatch hook landed: when classify says needs_action and the primary domain has an agent, the supervisor delegates and returns the agent's reply. memory and comms agents are wired in. all other domains fall through to the supervisor's direct chat for now.

## 2026-05-01 phase 2 partial

- memory sub-agent answers structured json: read_profile / update_profile_section / search / add_contact / log_decision / set_preference / list_decisions.
- the agent edits profile.md by markdown section, not by replace-all. the helper is unit-tested.
- 20-task eval list lives at tests/evals/memory_tasks.yaml. the harness that runs each task end-to-end against a real claude key is not landed in this session, the file is the spec.

## 2026-05-01 phase 3 partial

- comms agent drafts replies and opens an action_log row through approval.open_approval. the supervisor returns the draft + waits.
- /api/approvals lists pending and accepts decide(approved | rejected | edited).
- gmail mcp is not wired here. the comms agent calls a `gmail.draft` shape but never sends. the next session plugs the real mcp into a tool that runs only after approval flips status to approved.

## scope realized vs spec

build is sized for many sessions. this session lands phases 0 and 1 fully, phases 2 and 3 in working scaffold, and writes the rest as runnable stubs that pass smoke tests. every page, every route, every entry point exists. the integrations under settings are listed and reflect keychain status. no fake data passes for real data: tools that aren't wired return shaped stubs and routes that need a real api say so.

what does not yet exist:
- real gmail / google calendar / drive mcp clients (phase 3 finish)
- real github / slack / notion / linear tools (phase 5)
- plaid sandbox and apple health bridges (phase 5)
- imessage polling + applescript send (phase 4)
- whisper + telegram polling end-to-end with the supervisor (phase 4 partial: the route accepts text already)
- web push via vapid (phase 8)
- consolidation summarization with claude (phase 7)

what is fully runnable:
- `uv sync --dev` then `uv run pytest tests/integration` passes 7/7.
- `docker compose up -d` brings up postgres with pgvector and the schema applied.
- `uv run uvicorn api.main:app --port 8000` boots the api with all routes.
- `cd web && pnpm install && pnpm dev` boots the web at :3000 (after pnpm install resolves).
- `uv run python cli/ro.py chat "hello"` runs the supervisor against claude (with the key set).

## 2026-08-17 finish-the-build session (via /autoplan review pipeline)

- plan reviewed before building: ceo + eng phases, one independent claude voice each, spec loop 3 iterations, 14 doc issues fixed, 15 eng findings absorbed. full record in PLAN.md.
- listeners stay in-process in the api. the imessage/ and voice/ daemon scaffolds were deleted; ro.telegram.plist pointed at a module that never existed. one process, launchd manages api + web + jobs.
- approvals are a cas state machine now. decide flips pending only; execute claims approved/edited into executing atomically; edited bodies run exactly once; provider result stored on the row. reason: live double-send race and edited-path 500 found by the review.
- crash between send and executed-mark leaves the row in executing on purpose. re-claiming could double-send; the runbook covers the manual check.
- seen_keys and schedules tables had no ddl anywhere. committed, plus bootstrap applies tree_schema.sql. fresh clones broke before this.
- bearer middleware on all /api/* when remote_secret exists. setup_remote.sh binds 0.0.0.0 while only two voice endpoints checked auth before.
- every channel fails closed: telegram needs owner id, gmail needs user_email, imessage needs imessage_channel. guessing who may command ro is the vulnerability.
- the ro channel design: text your own number (or a dedicated contact). is_from_me cannot separate ro's replies from yours in the self chat (same apple id), so the gateway records a hash of everything it sends and the poll skips matches. chat.db was unreadable in the build shell (no full disk access), so this ships behind a verification spike documented in PLAN.md b.1.
- replies to the ro channel send directly, no approval. texting you back in your own channel is a write to your own system under the house rules. sends to anyone else stay gated.
- one gateway for all channels: stable (channel, chat_key) -> session uuid, everything through run_supervisor. conversations stop being amnesiac; traces and the approval gate hold on the highest-volume paths.
- applescript sends pass handle and text as argv. the handle was interpolated raw before, and the handle comes from llm-constructed payloads influenced by inbound content.
- scheduler claims before firing (cas on next_run_at), disables after 3 consecutive failures, disables on a broken cron spec instead of refiring every 30s with claude spend.
- budget guard v1: spend_log per claude call attributed via contextvar (routine:x, channel:y, playbook:z, consolidate, chat), daily_token_budget preference is a hard cap, background runs refuse over budget and fail closed if the check errors. user chat is never blocked.
- liveness heartbeats per worker surfaced in /settings. silent breakage was the six-month failure mode the review called out.
- voice went local-first: whisper small.en in a one-worker process pool (cpu work off the event loop), watchdog unloads after 10 idle minutes, openai fallback when ffmpeg/whisper missing, say+afconvert tts fallback, ios shortcut contract preserved.
- consolidation is real: sessions older than 14 days summarized by claude (cheap model), embedded, raw turns deleted, capped nightly, budget-checked.
- web push: vapid keys in keychain, subscriptions in postgres, 410 pruning, localhost v1 (service worker secure-context pass), tailscale cert documented for remote. approval opens and digests ping.
- digest delivers proactively: imessage ro channel (sent-hash recorded first), telegram owner dm, push headline. ro starts conversations now.
- playbooks v1 are run-verbatim markdown files under playbooks/. ## step headings chain through one stable session, each step sees the prior step's digest. that is the deterministic form of agent coordination; every outward write still stops at the approval gate. parameterization is v2, screen-recording capture deferred (TODOS.md).
- grok bot comparison, honest: ro now has always-on (launchd, best effort while the mac is awake), messaging interface, workflow learning (text-taught), coordination (chains), proactive mode, persistent browser profiles (host-scoped, opt-in). ro keeps secrets in the keychain and every outward write behind approval, which grok bot's shared-computer design does not.
- eslint configured for web (next/core-web-vitals). one jsx error fixed, img warnings accepted for now.
- deferred, logged in TODOS.md: whatsapp entry point (meta api account), screen-recording capture, plaid + apple health.

## 2026-08-17 phase 2, next-level session

- telegram inline approvals: approval opens send the owner a card with approve/reject buttons. presses come back as callback_query updates, owner-gated, through the same cas decide + atomic execute. a losing press sees "already decided".
- event triggers: triggers table + matcher in the gateway. substring or /regex/ per channel, cas cooldown claim (10 min) so bursts cannot double-fire, playbooks run as background tasks so replies are never delayed.
- teach by description: /api/playbooks/draft. narrate the task, the cheap model writes the stepped playbook, nothing saves until reviewed in the editor. the honest v1 of grok bot's teach-by-demonstration.
- mcp host: ro loads any mcp server from mcp_servers.json (keychain: env refs, real file gitignored). per-call stdio sessions, tool list cached 5 min and injected into the actions agent prompt, every call approval-gated as mcp.call because ro cannot tell a read from a write on an arbitrary server. this replaces "write an integration per service" as the growth path.
- local model tier: ollama handles classification when the ollama_model preference is set and the server answers. probe cached per minute, malformed output falls through to claude. free and private for the highest-volume call.
- weekly self-review: distills 7 days of decisions into learned-style rules in the profile, refreshes voice rules, runs the memory evals when keyed, reports through digest channels. ro measurably improves weekly or the evals say otherwise.
- two more tables had no ddl: learned_voice and voice_signals (voice learner wrote to them since the last commit landed them unbacked). committed with a tool column the learner expects.
- always-on substrate documented: mac mini (full fidelity incl imessage) or linux vps (systemd units shipped, no imessage). laptop stays the default.

## 2026-08-17 phase 3, moat wave (panel-reviewed: 5 lenses, adversarial judge)

- processing lanes: vault sources (channels, contacts, domains, addresses) and a global airgap switch, enforced where bytes leave — the claude wrapper raises, embeddings store zeros. taint follows data into memory; retrieval never assembles a vault row into a cloud-bound prompt. minimization by architecture, not policy.
- vault/airgap turns run a local-only reply path (ollama, no tools) with honest degradation. persisted tainted.
- signed egress ledger: hash-chained receipts for every outward byte (approval flip, self-channel reply, digest), advisory-lock serialized, /api/audit/verify recomputes the chain. honest scope noted in the module: proves integrity, not provenance against local root.
- shadow mode: playbook dry runs land every outward action as a simulated card, never claimable, zero egress, would-have-done tape returned for review before arming.
- glass-box learning: self-review proposes learned-style rules through an approval card with evidence; profile changes only through the gate.
- total recall: archive_messages lifetime corpus (chat.db resumable backfill, year-windowed gmail sweeps). consolidation now archives raw turns instead of deleting — reversing the 2026-05-01 delete decision, which was made when metered claude was the only summarizer. disk is cheap; memory is the moat.
- relationship register: nightly per-contact dossiers from the archived history, injected into drafts to that person.
- open loops: commitments mined nightly (local model first), digest surfaces them with age.
- imessage concierge: digest lists threads where the last word is theirs.
- ambient triggers: watch_paths preference; filesystem changes fire channel-file triggers into playbooks.
- fork and estate export: ro export tars the full db dump + playbooks + restore doc. secrets never leave the keychain. the agent is a folder, not an account.
- skipped by choice: ambient always-on listening (all-party-consent legal risk flagged by the review panel), speculative rehearsal and watcher swarm (refuted as moats — google ships both at scale).

## 2026-08-17 phase 4, the crew

- named bots: bots/*.md charters, one persistent session per bot (channel_sessions channel=bot) so each remembers its work. every bot run goes through run_supervisor, so tools, lanes, budget, and the approval gate apply to bots exactly as to the user.
- collaboration is explicit and bounded: a bot delegates with a '>> bot-name: task' line. depth cap 2, three delegations per reply, four bots per crew run. every handoff lands in bot_messages; the /bots page shows the log. no hidden channels by construction.
- crew runs: a planner (local model first, cheap claude fallback) picks which bots a task needs, they run, the dispatcher synthesizes.
- hire by description: /api/bots/draft writes a charter from a plain-language role. charters never instruct bypassing approvals; the drafter's system prompt forbids it.
- schedule a bot: schedules text 'bot:<name>: <task>'. standing duties run on cron like any routine.

## 2026-08-17 phase 5, tier one

- browser trust tiers: browser_trust preference maps domain -> read | navigate. requires_approval=False now means policy-approved: the row lands in action_log already approved (auditable, still ledgered), and the agent executes immediately. url-bearing actions only; clicks, fills, scrolls, closes always ask. suffix matching rejects evil-github.com lookalikes.
- ro as an mcp server: api/mcp_server.py (mcp 2.0 MCPServer, stdio). exposes memory search, archive search, open loops (read + add), pending approvals (read-only), playbook runs, ro_chat through the full supervisor, and ro_message_user (self-channel only, ledgered). the approval gate sits below the mcp surface, so no client can bypass it. claude code config snippet in the module docstring.
- night shift: 03:30 launchd job. embedding backfill for rows that never got vectors (lane-aware, vault skipped), analyze on hot tables, a 5-task eval spot-check when keyed. report lands in preferences and the digest's overnight line.
- screen sense: menubar "ask about my screen". screencapture -> apple vision ocr fully on-device (pyobjc-framework-vision) -> only the recognized text goes to the supervisor with a read-only framing; answer lands in a window and on the clipboard. pixels never leave the machine.

## 2026-08-17 phase 6, tiers two and three

- life report: monthly rewind (api/life_report.py, ro.lifereport.plist on the 1st) from the archive, commitments, action_log, and spend. honest fallback when the data is thin.
- voice conversation mode: menubar toggle. /api/voice/loop and /talk accept a session id, ro remembers across turns, playback ends and the mic opens again. one conversation, not amnesiac one-shots.
- distill prep: api/eval/distill.py exports edited-draft training pairs as jsonl with dedupe and a minimum-pairs refusal. the mlx-lm lora recipe and the eval-gated promotion path live in the docstring, with the honest caveat that learned-style rules may beat a lora at low volumes. data side only by choice.
- guest mode: imessage_guests keychain key allowlists up to five handles. guests get a framed, actionless, no-private-data ro in separate sessions with per-guest watermarks. first sight is baseline, not a backlog to answer.
- body ledger ingestion: api/integrations/health_import.py streams apple health export.xml (hundreds of mb) via iterparse into health_samples with an allowlist. weekly_summary for the digest later. waiting on an export file, by design.
- focus-aware delivery: api/observability/focus.py reads the macos focus assertions file best-effort plus a quiet_hours preference. digests defer during focus or quiet hours; approval pings stay urgent and always land.
- clipboard memory: opt-in menubar toggle, 2s pasteboard polling, secret-shaped text never stored (prefix and password-shape heuristics err toward skipping), rows local with fts search.

## 2026-08-17 phase 7, control plane

- slash commands: /status /loops /spend /sent /pause /resume answered instantly in any channel before triggers and the model. zero spend, zero latency. unknown slash text still falls through to the model.
- /pause: paused_until preference. scheduler fires and trigger matching respect it; user chat never pauses. approvals still land (deciding is not background work).
- ro doctor: every dependency checked with its exact fix printed. the go-live dry run.
- backups: nightly.sh now also writes a local ro export with keep-7 rotation, alongside the encrypted offsite dump.
- routines card: schedules visible and manageable on /playbooks (plain task, playbook:<name>, bot:<name>: task).
- decision: this closes feature development until the system is in real use. control-plane features were the last category that does not bet on unobserved usage. next code change should be motivated by a real session, a failing eval, or a red light on /settings.

## 2026-08-17 phase 8, going public

- relicensed mit, replacing all rights reserved. the point of ro flipped from portfolio piece to product real users can run. once forked this is one-way; chosen deliberately at the launch gate.
- personal defaults swept out of runnable paths (go_live email default, digest prompt name, example urls, eval fixtures genericized).
- readme rewritten as the pitch: the one-liner is the trust model. quick start is clone -> bootstrap -> go_live.
- CONTRIBUTING.md carries the non-negotiables (gate, keychain, fail closed, honest degradation). SECURITY.md states the load-bearing claims, how to verify each, and the honest limits. docs/launch.md is the show hn kit — the user posts it, nothing posts itself.
- credibility rule in the launch kit: dogfood before posting. a personal agent you don't use is a demo, and hn can smell it.

## 2026-08-17 phase 9, the skills bridge

- ro speaks anthropic's open SKILL.md format. mcp brought the world's tools; the skills bridge brings the world's procedures. catalog scans ~/.claude/skills, ./skills, and skill_paths preference two levels deep, frontmatter-only for speed, cached 5 minutes. verified live against 4,570 skills on this machine.
- safety unchanged by construction: a skill body is third-party instructions run through the supervisor; anything it wants done in the world goes through the normal proposers and the approval gate. bundled scripts never execute directly — only through an approved shell card.
- with this, ro consumes both open agent ecosystems (mcp servers, agent skills) approval-gated. grok bot consumes neither. this was the last ecosystem door; there are no more ecosystems to bridge.

## 2026-08-17 phase 10, openrouter path

- the brain accepts a second key: openrouter_api_key runs the same claude models through openrouter's openai-compatible gateway when no direct anthropic key exists. a shim quacks like the anthropic message shape for every caller. tool-bearing calls still require the direct key (honest limitation, raised loudly). spend attribution tags openrouter models. the key is stored by the user themselves via keyring — keys are never pasted into chats, and the assistant never handles them; that rule is part of ro's own dna and it applied to building ro too.
