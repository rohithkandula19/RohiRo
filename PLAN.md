# plan: finish ro end to end

goal: every capability in ro works for real. no stubs, no shaped fake data, no idle daemons. clean repo, tests passing, pushed to origin.

## current state

- phases 0-1 done: supervisor pipeline, 12 web routes, command palette, sse streaming, memory agent, comms agent scaffold, approvals api.
- integrations written but not all verified: gmail, gcal, gdrive, github, slack, notion, linear, telegram, imessage, browser, voice, vision, system, whatsapp (3241 lines total).
- entry point daemons are no-op scaffolds: imessage/listener.py idles, voice/handler.py partial, telegram polling not wired.
- eval harness spec exists (memory_tasks.yaml) but the runner is not landed.
- desktop menubar app exists but unpolished.

## a. repo hygiene (remove unnecessary)

1. remove stray runtime dirs from working tree root: .pytest_cache (untracked but noise).
2. audit and remove dead code: unused fixtures dirs, empty placeholder files. whatsapp.py stays parked (deferred entry point, see non-goals), not deleted.
3. verify .gitignore covers all runtime data (postgres-data, redis-data, langfuse-data already covered). confirm nothing tracked that should not be.
4. dedupe docs: README, DECISIONS.md stay. remove any generated artifacts that do not belong.
5. create TODOS.md holding the deferred items (whatsapp, screen-recording capture, plaid + apple health).

## b. entry points become real (spec phase 4)

1. imessage: listener daemon polls chat.db read-only for new messages in the ro channel, forwards to supervisor /api/chat, sends reply via applescript. rate-limit, dedupe on message rowid. loop prevention: in the self-chat both the user's phone-sent messages and ro's replies are recorded as sent under the same apple id, so is_from_me cannot discriminate. first task is a verification spike inspecting real chat.db rows for a phone-sent self-message; the committed design tracks the guids of messages ro itself sent via applescript and skips only those, with a dedicated contact channel as fallback if the spike disproves self-chat viability. approval flow respected (outward sends still gated). setup step documents macos full disk access (chat.db read) and automation permission (applescript send) for the launchd context.
2. telegram: long-poll getUpdates loop, token from keychain, routes text to supervisor, replies inline. approval requests render as inline approve/deny buttons.
3. voice: /api/voice accepts audio, whisper local (small.en default) transcribes, routes text to supervisor, returns text + optional local tts reply. ios shortcut doc already exists.

## c. integrations verified through approval flow (spec phases 3+5)

1. gmail: comms agent drafts via gmail.create_draft, approval flips to approved -> send_draft executes. inbound triage read path wired to /inbox route.
2. gcal: calendar agent reads events, creates events through approval.
3. gdrive: files agent search + fetch.
4. github: code agent lists prs/issues, comments through approval.
5. slack, notion, linear: same pattern, read free, write gated.
6. each integration: configured() check surfaces in /settings with keychain status.

## d. background intelligence (spec phases 6-8)

1. scheduler: engine runs registered routines (morning digest, inbox sweep) on cron-like schedule.
2. memory consolidation: nightly claude summarization pass over episodic rows into semantic memory (consolidate.py finished).
3. web push: vapid keys in keychain, subscribe endpoint, push on approval-needed and digest-ready. scoped to localhost origin for v1 (service workers need https elsewhere); tailscale cert for https noted in docs as the remote-push path.
4. budget guard: monthly api budget in settings, per-routine token accounting on top of the claude.py wrapper's token logging, scheduler refuses to start new routine runs when the budget trips. spend visible in /settings.

## e. quality gates

1. eval harness runs memory_tasks.yaml end to end against a real key (skippable in ci without key).
2. integration tests extended: supervisor happy path, one per entry point (mocked transports).
3. approval flow is the most tested path in the system: adversarial test that attempts an outward send without an approved row must fail closed. playbooks and agent chains route outward writes through the same gate.
4. prompt injection defense: all fetched content (email bodies, web pages) treated as untrusted. browser agent autonomous navigation restricted to an allowlist; anything else needs approval. one eval attempts injection via the inbox triage path.
5. integration liveness: /settings shows not just keychain status but a live self-check per integration (last successful call), so silent breakage is visible.
6. pnpm build green, uv run pytest green, lint green.

## f. desktop + docs polish

1. menubar app: status, pending approvals count with quick approve/deny from the menu, open web ui.
2. README updated to reflect real state, quick start verified.
3. DECISIONS.md entries appended for every choice made here.

## h. beyond grok bot (expansion scope, user-approved)

1. always-on: launchd agents for api, imessage listener, telegram poller, scheduler. `ro up` / `ro down` cli to manage them. honest posture: best effort while the mac is awake; routines catch up on wake rather than pretending 24/7. survives reboot.
2. workflow learning: "teach ro" flow. v1 is run-verbatim playbooks: user describes a task in chat, ro saves it as a markdown playbook file under memory/playbooks/, runnable on schedule or on demand, listed and editable via chat and web. parameterization and branching are v2. playbooks never bypass the approval gate.
3. agent coordination: supervisor can dispatch multi-agent chains (research agent output feeds comms agent draft). traces show the chain. group-chat style thread view in web ui is a stretch item, not core.
4. persistent browser sessions: wire browser.py (517 lines, exists) into agents with a persistent profile dir so logged-in sites stay logged in. approval-gated for any submit.
5. proactive mode: routines can message you first (morning brief via imessage/telegram push, approval-needed pings). ro starts conversations, not just answers.

## g. ship

1. conventional commits per logical unit.
2. push to origin https://github.com/rohithkandula19/RohiRo.git main.

## success metrics (measured 2 weeks post-ship)

- ro used via chat on 10+ of 14 days.
- morning digest delivered and opened 5+ days/week.
- 5+ outward drafts approved and sent through the gate, zero unapproved sends.
- zero silent integration failures (liveness check green or visibly red).
- api spend within a set monthly budget; per-routine token use logged, kill switch trips over budget.

## non-goals

- whatsapp entry point (integration file parked, needs meta business api account). logged in TODOS.md.
- screen-recording demonstration capture (text-taught playbooks first; revisit after they prove out). logged in TODOS.md.
- plaid sandbox and apple health bridges (finance/health agents keep read-only manual import for now, logged in TODOS.md).
- multi-user, auth hardening beyond localhost + tailscale.
- app store distribution of the desktop app.

## hard rules carried over

- secrets only from macos keychain via keyring. never env, never committed.
- outward writes always pause on approval interrupt.
- repository pattern for db access, no raw sql in agents.
- writing style: no em dashes, sentence case, short sentences.

## review outputs (phase 1, ceo review via /autoplan)

### architecture (section 1)

```
  ENTRY POINTS                 CORE                          OUTBOUND
  imessage listener --http--> /api/chat (supervisor) ----> agents ----> integrations
  telegram poller   --http--> /api/chat        |             |            gmail gcal gdrive
  voice /api/voice  --------> supervisor       |             |            github slack notion
  web ui / cli      --------> supervisor       v             v            linear browser
                                        memory (pg+pgvector)  approvals (action_log)
  scheduler --routines/playbooks--> supervisor         gate: outward writes pause here
  push service <-- approval-needed, digest-ready       menubar/web/telegram buttons decide
  budget guard: scheduler asks before each routine run; claude.py logs tokens per run
```

- daemons are thin http clients to the api, never import the app. isolation and independent restart.
- single points of failure: postgres (memory + approvals) and the api process. launchd keepalive restarts both paths; daemons back off and retry while api is down.
- new surfaces: /api/voice, /api/push/subscribe, /api/playbooks, /api/health. localhost + tailnet only, single user posture, unchanged.
- rollback: all migrations additive, `ro down` stops daemons, git revert restores. no destructive migration in this plan.

### error and rescue registry (section 2)

```
  codepath                  | what can go wrong               | rescued | action                        | user sees
  --------------------------|---------------------------------|---------|-------------------------------|----------
  imessage poll (chat.db)   | db locked / wal busy            | y       | skip tick, retry next         | nothing
                            | full disk access revoked        | y       | log + push alert + settings red| red status
                            | schema change (macos update)    | y       | fail closed, alert            | red status
  applescript send          | automation permission denied    | y       | queue reply, alert            | red status
                            | osascript timeout               | y       | retry 2x then queue           | delayed reply
  telegram getUpdates       | network drop / timeout          | y       | backoff reconnect             | nothing
                            | 409 conflict (two pollers)      | y       | exit duplicate, log           | nothing
                            | invalid token                   | y       | fail closed, settings red     | red status
  gmail send_draft          | oauth token expired             | y       | refresh, else settings red    | red status
                            | 429 rate limit                  | y       | backoff retry                 | delayed send
  scheduler routine run     | routine crashes                 | y       | log failure, next tick        | run marked failed
                            | previous run still in flight    | y       | skip (no overlap)             | run marked skipped
  whisper transcribe        | unreadable audio / empty        | y       | reply "could not hear that"   | error message
                            | model load oom                  | y       | fall back to base model       | slower reply
  web push send             | subscription gone (410)         | y       | delete subscription           | nothing
  playbook run              | referenced integration missing  | y       | halt playbook, report step    | failure message
                            | step fails mid-run              | y       | halt, report completed steps  | partial report
  budget guard check        | db unavailable                  | y       | fail closed (no new runs)     | paused notice
  browser action            | nav timeout / login expired     | y       | halt, request human takeover  | approval prompt
  claude call (all agents)  | malformed / refusal / empty     | y       | 1 retry, then honest error    | error message
```

no unrescued gaps remain in the design. catch-alls are banned; each handler names its exception.

### security and threat model (section 3)

- telegram inbound: allowlist the user's chat id in settings. without it anyone who finds the bot controls ro. likelihood high, impact high, mitigated by allowlist + fail closed when unset.
- imessage inbound: accept only the ro channel (self chat or dedicated contact per b.1 spike). likelihood med, impact high, mitigated.
- applescript send: reply text is interpolated into an osascript call. escape via argv passing (no string interpolation). likelihood med, impact med, mitigated.
- prompt injection via fetched content: covered by e.4 (untrusted content, browser allowlist, injection eval).
- playbooks: run through the supervisor so outward writes hit the approval gate. playbook files are user-editable markdown; no secrets inside, validated on load.
- new dependencies (whisper binding, pywebpush, httpx telegram): pinned versions, no post-install scripts, reviewed at add time.
- secrets: unchanged keychain-only rule. vapid keys and telegram token land in keychain.
- audit: action_log already records every outward write and decision. daemons log sends with message ids.

### data flow edge cases (section 4)

- imessage dedupe: last processed rowid persisted in postgres, not process memory. restart-safe, no double replies after kill -9.
- telegram offset: update offset persisted the same way.
- approval double-decide: deciding an already decided approval is a no-op with a friendly message. status transition guard in repo layer.
- routine overlap: scheduler skips a tick if the previous run of the same routine is still running.
- voice empty transcript: short-circuit with "could not hear that", never sends empty text to supervisor.
- digest with zero items: sends "quiet day" digest, never an empty push.
- playbook edited while a run is in flight: run continues on the loaded copy, next run picks up the edit.

### code quality (section 5)

- daemons share one inbound gateway helper (route text -> supervisor -> reply callback) so imessage and telegram do not duplicate orchestration.
- match existing conventions: async first, repository pattern, single claude wrapper, structured log lines, lowercase docs.
- no new frameworks for playbooks v1: markdown files + a loader, no plugin system.
- naming: listener, poller, playbook, routine, guard. no cleverness.

### test review (section 6)

```
  new flows -> tests
  imessage inbound reply     integration (mocked chat.db rows + mocked applescript)
  ro-sent guid skip          unit
  telegram inbound + buttons integration (mocked transport)
  approval gate              adversarial integration: attempt send without approved row -> must fail closed
  gmail send after approval  integration (mocked gmail client, real approval flow)
  scheduler catch-up on wake unit (frozen clock)
  routine overlap skip       unit
  budget guard trip          unit (spend fixture over budget -> refuse)
  playbook load + run        unit (parser) + integration (halt on missing integration)
  whisper pipeline           integration (fixture wav -> mocked model)
  consolidation nightly      integration (mocked claude, episodic fixtures -> semantic rows)
  push subscribe + send      unit (mocked webpush, 410 pruning)
  injection eval             eval (hostile email fixture tries to trigger outward send)
  memory tasks               eval (memory_tasks.yaml via harness)
```

- 2am friday test: the approval adversarial test.
- hostile qa test: injection eval.
- chaos test: kill listener mid-poll, restart, assert no duplicate reply (watermark test).
- flakiness: no real network in tests, clock injected, whisper mocked.

### performance (section 7)

- chat.db polled read-only every 2s: negligible. telegram long-poll: one idle connection.
- whisper small.en loads ~500mb transiently: lazy load, release after 10 idle minutes.
- nightly consolidation batches embeddings; ivfflat index already present.
- new indexes: action_log(status), watermarks(channel), routine_runs(routine_id, started_at).
- worst new path: playbook chaining multiple agent calls; bounded by budget guard and per-run step cap.

### observability (section 8)

- every daemon: structured entry/exit/error logs plus a heartbeat row (last_seen) surfaced in /settings liveness (e.5).
- metrics that matter: replies sent per channel, approval latency, routine success rate, spend per routine. all visible in /settings or overview.
- self-alerting: repeated daemon failure triggers a push + digest line. ro reports its own broken arms.
- traces: langfuse spans already wrap claude calls; daemons pass a request id through to the supervisor.
- runbooks: docs/runbook.md gets one entry per failure mode in the registry above.

### deployment and rollout (section 9)

- order: migrate (additive tables: watermarks, playbooks, push_subscriptions, budget, routine_runs) -> restart api -> `ro up` daemons.
- feature flags: per entry point enable toggle in settings, default off until configured. safe first boot.
- rollback: `ro down`, git revert, restart. no data loss (additive only).
- smoke: scripts/smoke.sh hits /api/health, posts a chat roundtrip, checks daemon heartbeats.
- post-deploy checklist: settings page all green, send one self message, approve one test draft.

### long-term trajectory (section 10)

- debt accepted knowingly: applescript send and chat.db polling are apple-fragile. mitigated by liveness alerts and the dedicated-contact fallback. logged, not hidden.
- reversibility 4/5: everything additive, daemons removable, tables droppable.
- platform potential: playbooks + scheduler + approval gate are the substrate for v2 parameterized workflows and deeper agent chains.
- the durable assets are the memory corpus, playbooks, approval history, and evals. integrations stay thin and replaceable by design (outside voice finding, absorbed).
- build vs adopt note: the custom stack is kept because privacy (keychain, local db), the approval interrupt model, and the learning value are the differentiated core. plumbing that commoditizes (transport polling, push) stays minimal.

### design and ux (section 11)

skipped: no ui scope detected (ui deltas are additive rows on existing pages: settings liveness, spend, playbook list, menubar approve). /plan-design-review recommended only if the thread view stretch item is picked up.

### not in scope

- whatsapp entry point, screen-recording capture, plaid + apple health (TODOS.md).
- multi-user, https hardening beyond tailscale cert note, app store distribution.
- playbook parameterization and branching (v2).

### what already exists

- integrations: 3241 lines across 16 modules, all reused as-is, wiring only.
- supervisor, approvals api, memory layer, scheduler engine, eval spec, browser automation, menubar scaffold: all reused.
- nothing in this plan rebuilds existing code.

### dream state delta

after this plan: daily driver with every entry point live and grok-bot-parity features (always-on, playbooks, coordination, proactive). remaining gap to 12-month ideal: parameterized workflows, richer multi-agent autonomy, hosted daemon substrate.

### ceo dual voices, consensus table (subagent-only, codex not installed)

```
  dimension                             claude voice   codex   consensus
  ------------------------------------- -------------- ------- -----------------
  1. premises valid?                    partial        n/a     absorbed (build-vs-adopt note added)
  2. right problem to solve?            partial        n/a     taste decision td1 (breadth vs focus)
  3. scope calibration correct?         no             n/a     taste decision td2 (gate h behind usage?)
  4. alternatives sufficiently explored? no            n/a     absorbed (a/b/c defined, build-vs-adopt noted)
  5. competitive/market risks covered?  no             n/a     absorbed (durable-assets investment note)
  6. 6-month trajectory sound?          partial        n/a     absorbed (metrics, budget, liveness, injection defense added)
```

single-voice findings absorbed into the plan: success metrics section, d.4 budget guard, e.4 injection defense, e.5 liveness, honest always-on posture, thin replaceable plumbing. two strategy disagreements survive as taste decisions for the final gate.

<!-- AUTONOMOUS DECISION LOG -->
## decision audit trail

| # | phase | decision | classification | principle | rationale | rejected |
|---|-------|----------|----------------|-----------|-----------|----------|
| 1 | ceo | approach b (full completion) over minimal or rewrite | mechanical | p1, p4 | user premise-confirmed breadth; rewrite discards working code | a, c |
| 2 | ceo | dx phase skipped | mechanical | p3 | single-user personal tool, api/cli matches are self-referential | run dx review |
| 3 | ceo | design phase skipped | mechanical | p3 | under 2 ui term matches; ui deltas are additive rows | run design review |
| 4 | ceo | telegram buttons, tts replies, menubar approve added | mechanical | p2 | in blast radius, small | defer |
| 5 | ceo | whatsapp, screen recording, plaid/health deferred | mechanical | p2, p3 | external deps or new subsystems outside radius | build now |
| 6 | ceo | workflow learning v1 = run-verbatim playbooks | mechanical | p5 | reviewer showed m was optimistic; verbatim first | parameterized v1 |
| 7 | ceo | is_from_me filter replaced with guid tracking + spike | mechanical | p1 | reviewer proved filter breaks self-chat flow | keep filter |
| 8 | ceo | absorbed 6 single-voice strategy findings into plan | mechanical | p1, p6 | each was in blast radius and concrete | ignore voice |
| 9 | ceo | breadth kept over 3-workflow focus | taste td1 | user direction | user said "everything, more than grok bot"; voice argued focus | focus |
| 10 | ceo | h built now, not gated behind 2-week usage | taste td2 | user direction | user raised ambition explicitly; voice argued evidence first | gate h |
| 11 | eng | listeners stay in-process in the api; daemon scaffolds deleted | mechanical | p4, p5 | api/listeners/ already exists and works; parallel daemons would duplicate it and double-reply | extract to daemons |
| 12 | eng | approval transitions become sql compare-and-swap | mechanical | p1 | live double-send race + broken edited path found by voice, confidence 9 | politeness check |
| 13 | eng | bearer middleware on all /api/* always | mechanical | p1 | setup_remote.sh binds 0.0.0.0 with only 2 authed endpoints | localhost assumption |
| 14 | eng | budget guard v1 = persisted daily cap + per-run attribution; contextvar plumbing sized honestly | mechanical | p3 | voice showed the checkbox was a workstream | full attribution v1 |
| 15 | eng | whisper local kept (repo spec) but in a process pool, ios contract preserved | mechanical | p5 | DECISIONS.md commits to local voice; event-loop stall fixed by pool | revert to openai api |
| 16 | eng | playbook/listener-originated approvals get structural constraint (reply-to-origin only, shell needs extra confirm) | mechanical | p1 | stronger than eval-only defense against rubber-stamping | eval only |

## review outputs (phase 3, eng review via /autoplan)

### step 0 scope challenge

- complexity check triggers (plan touches far more than 8 files). autoplan override: never reduce, proceed as-is. the plan is a finish-the-build across independent workstreams, each shippable alone.
- existing code leverage correction: api/listeners/ (imessage, telegram, email, ~500 lines) already exists and runs in-process from the api lifespan. api/supervisor/ exists with approval.py, execute.py, graph.py. the eval harness and 16 agents landed in the last commit. the plan's "daemons are thin http clients" claim was wrong about the current repo.
- repo sync: local main is behind origin/main by 1 commit. workstream g starts with pull --rebase.

### eng findings absorbed (15 findings, all accepted)

1. listener home decided: listeners stay in-process in the api. delete imessage/ and voice/ scaffold dirs, fix or regenerate launchd plists (ro.telegram.plist points at a nonexistent module and would crash-loop under keepalive). `ro up` manages api + web + scheduler only.
2. approval state machine hardened: every transition is a sql compare-and-swap (approve: set approved where status=pending returning; execute: set executing where status=approved returning). edited decisions are approvable and execute the edited body exactly once. provider message id recorded in the claim row. crash between send and mark cannot re-send.
3. tests target the real failure modes: concurrent double-approve (one send), edited-path exactly-once, card fidelity (what was displayed is what executes; fix payload key mismatch handle vs recipient in execute._describe), fresh-db bootstrap, fail-closed defaults per channel.
4. seen_keys table gets committed ddl (it is used by five modules and defined nowhere). the planned watermarks table is dropped; listeners keep seen_keys, migrated to single-row upserts per channel.
5. auth: bearer middleware on all /api/* regardless of bind. token never in url query params. telegram callback approvals must match telegram_owner_id.
6. fail closed everywhere: telegram listener refuses to start without owner id. email listener refuses without user_email. imessage accepts only the ro channel. one addressing policy, enforced in the shared gateway helper.
7. applescript: both handle and text passed as argv (on run argv), never interpolated. scheduler _notify gets the same fix.
8. scheduler: claim row before fire (cas on next_run_at), routine_runs row written before execute, disable after n consecutive failures, budget guard vetoes re-fires, compute_next failure disables the schedule instead of refiring every 30s.
9. budget guard resized: v1 is a persisted daily spend cap (postgres, fail closed) plus per-run attribution via contextvar through the claude wrapper. retry accounting includes the fallback-model path. connection errors join the retry policy.
10. all inbound channels route through run_supervisor via the shared gateway with a stable (channel, chat_id) -> session uuid map. no more direct comms_agent.run() bypass, no more amnesiac conversations.
11. gmail _extract_body walks parts recursively (nested multipart/alternative inside mixed).
12. /api/chat validates history (roles user/assistant only, length cap). session ids server-issued where feasible.
13. voice stays local whisper per repo spec, but transcription runs in a process pool, model watchdog unloads after idle, ios shortcut contract (mp3 out, x-ro-* headers) preserved by tests.
14. playbook and listener-originated approvals carry a structural constraint: reply only to the originating sender, never new recipients, shell.run from a playbook needs an explicit extra confirm. shell_safety flags render on the approval card.
15. deploy hygiene: whatsapp webhook default off behind the entry-point flags. scheduler "once" tz semantics fixed to schedule tz, documented. workstream g starts with git pull --rebase.

### failure modes registry (delta found by eng voice, all now fixed in design)

```
  codepath                     | failure mode                       | fixed by
  -----------------------------|-------------------------------------|---------
  approvals decide+execute     | double-send race, edited 500        | cas transitions (finding 2)
  fresh clone bootstrap        | seen_keys undefined table           | committed ddl (finding 4)
  scheduler compute_next error | 30s claude refire loop, spend leak  | disable + claim (finding 8)
  scheduler crash mid-fire     | duplicate digest on restart         | claim before fire (finding 8)
  0.0.0.0 bind                 | unauthenticated approve/chat/settings| bearer middleware (finding 5)
  telegram owner unset         | anyone controls ro                  | fail closed (finding 6)
  applescript handle           | osascript injection                 | argv passing (finding 7)
  dual listeners during cutover| double replies                      | in-process decision (finding 1)
```

### eng dual voices, consensus table (subagent-only, codex not installed)

```
  dimension                     claude voice   codex   consensus
  ----------------------------- -------------- ------- ---------------------------
  1. architecture sound?        partial        n/a     fixed: listener home decided
  2. test coverage sufficient?  no             n/a     fixed: race/fidelity/bootstrap tests added
  3. performance risks?         partial        n/a     fixed: process pool, claim loop
  4. security threats covered?  partial        n/a     fixed: middleware, fail closed, argv
  5. error paths handled?       partial        n/a     fixed: registry delta absorbed
  6. deployment risk?           partial        n/a     fixed: cutover, plists, pull first
```

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 1 | issues_open (via /autoplan) | 12 proposals, 9 accepted, 3 deferred |
| Codex Review | `/codex review` | Independent 2nd opinion | 1 | issues_found (claude fallback) | 11 strategy findings, 6 absorbed |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | issues_open (via /autoplan) | 15 issues, 0 critical gaps remaining |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | skipped | no ui scope detected |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | skipped | single-user tool, no dev-facing scope |

**CROSS-MODEL:** codex not installed; both voices were independent claude subagents. spec review loop: 3 iterations, 14 issues fixed, PASS 9/10.

**VERDICT:** CEO + ENG reviewed with all findings absorbed into the plan — ready to implement once the final gate's 2 taste decisions are answered. eng review status flips to clean when the P1 task list lands.

**UNRESOLVED DECISIONS:**
- td1: breadth (all capabilities) vs 3-workflow focus — user direction is breadth, ceo voice argued focus
- td2: build workstream h now vs gate behind 2 weeks of usage evidence — user direction is now, ceo voice argued evidence first