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
