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
