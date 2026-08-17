# ro

**a team of AI agents that lives on your own Mac — and can't send a single byte without your yes.**

ro is a personal agent operating system: one user, local first, open source.
text it from your phone, teach it playbooks in plain words, hire named bots
that collaborate, and let routines run while you sleep. your memory lives in
your postgres, your secrets live in your keychain, and every outward action
stops at an approval card with a hash-chained receipt you can verify.

the cloud alternatives charge $200-300/month and run your life on a shared
computer under someone else's terms. ro runs on hardware you own, under rules
you can read, with a model tier that works fully offline.

## what it does

- **text your own number.** the imessage listener watches your ro channel
  (self chat or a dedicated contact) and replies in seconds. telegram works
  the same. conversations keep context: one stable session per channel.
- **inbox and calendar.** gmail triage, reply drafting behind approval
  cards, calendar reads and gated event creation.
- **playbooks.** teach ro a task once in markdown. `## step` headings chain
  steps through one session, each step seeing the last one's output. run on
  demand or on a schedule (`playbook:<name>`).
- **routines.** cron schedules fire through the supervisor. the morning
  digest builds itself and messages you first: imessage, telegram, push.
- **memory.** postgres + pgvector hybrid retrieval, nightly consolidation:
  old sessions get claude-written summaries, raw turns compact away.
- **approvals everywhere.** every outward write pauses on an approval card:
  web, menubar (approve from the menu), or your phone. the state machine is
  compare-and-swap: nothing double-sends, edited drafts run exactly once.
- **budget guard.** every claude call is attributed (routine, channel,
  playbook, chat). set a daily token cap; background runs refuse over it.
- **liveness.** every worker heartbeats. /settings shows green or red, and
  ro pings you when one of its own arms breaks.
- **voice.** local whisper in a process pool, ios shortcut round-trip
  (audio in, audio out), openai fallback when local pieces are missing.
- **mcp host.** drop any mcp server into `mcp_servers.json` and ro gains
  its tools, every call behind the approval gate. secrets stay keychain
  refs, never in the file.
- **triggers.** when a matching message arrives on any channel, a playbook
  fires in the background. substring or regex, per-channel, with cooldowns.
- **teach by words.** describe a task in plain language and ro drafts the
  stepped playbook for your review.
- **phone approvals.** telegram cards with approve/reject buttons; presses
  go through the same race-safe gate as every other surface.
- **self-review.** weekly, ro distills your edits and rejections into
  style rules, refreshes its voice, and runs its evals to prove it didn't
  get worse.
- **local model tier.** with ollama running, classification goes local:
  free, private, sub-second. claude stays the brain.
- **vault lanes + airgap.** tag sources as vault (a contact, a channel, a
  domain) and they are only ever processed on-device — the taint follows
  the data into memory, so vault rows never enter a cloud-bound prompt.
  airgap mode does it for everything, with a switch.
- **signed egress ledger.** every outward byte gets a hash-chained receipt
  minted at the approval gate. /api/audit/verify recomputes the chain:
  "nothing sent without your yes" is a query, not a promise.
- **total recall.** backfill your entire chat.db and gmail into a lifetime
  local corpus with no retention limits. consolidation archives, never
  forgets. ask what the landlord promised in 2019.
- **relationship register.** nightly per-person dossiers from your whole
  shared history; drafts to that person sound like you-with-them.
- **open loops.** promises mined from sent messages, both directions,
  surfaced in the digest until closed.
- **shadow mode.** dry-run any playbook against the real supervisor with
  guaranteed zero egress; review the would-have-done tape before arming.
- **ambient triggers.** filesystem changes fire playbooks. a datacenter
  bot cannot see your Downloads folder move.
- **the crew.** hire named bots with markdown charters. they delegate to
  each other with an explicit `>> bot: task` protocol, depth-capped, every
  handoff logged — no hidden channels, by construction. run one bot or
  give the whole crew a task and let the planner assign it.
- **slash commands.** text `/status`, `/loops`, `/spend`, `/sent` in any
  channel for instant answers with no model call. `/pause 2` silences all
  background automation for two hours; your own chat keeps working.
- **conversation mode.** menubar toggle: talk, ro answers aloud, the mic
  reopens, the thread continues. voice with memory, not one-shots.
- **screen sense.** hotkey a screenshot through on-device apple vision
  ocr and ask ro about it. the pixels never leave the machine.
- **browser trust tiers.** allowlist domains as read or navigate and the
  boring browser actions stop asking. policy-approved actions stay in the
  audit history and the ledger; clicks and form fills always ask.
- **night shift.** at 3:30am ro embeds unvectored memories, runs db
  hygiene, and spot-checks its evals on free local compute. the digest
  reports what happened overnight.
- **guest mode.** allowlist a few handles and family can text your ro — a
  framed, actionless ro that treats your private data as off-limits, in
  fully separate sessions.
- **life report.** on the 1st of the month, ro writes your month: who you
  talked to, loops opened vs closed, what it did, what it cost.
- **body ledger.** import your apple health export into local postgres;
  weekly summaries join the rest of your life without a cloud health
  processor in the loop.
- **clipboard memory.** opt-in menubar toggle; secret-shaped text is
  never stored, everything else becomes searchable.
- **focus-aware.** digests defer during macos focus modes and your quiet
  hours. approval pings stay urgent and always land.
- **ro as an mcp server.** point claude code (or any mcp client) at
  `api.mcp_server` and your other tools get ro's memory, archive, loops,
  and channels — with the approval gate below the surface where no
  client can reach.
- **fork & export.** `ro export` tars your entire agent — memory, history,
  ledger, playbooks — restorable anywhere. a folder, not an account.
  nightly backups rotate the last seven automatically.

## what's in here

a turborepo monorepo.

- `web/` next.js 14 ui. every domain a route, plus playbooks and settings
  (liveness, spend, push).
- `api/` fastapi + langgraph supervisor and sub-agents. listeners run
  in-process: imessage, telegram, gmail. scheduler, budget, heartbeats,
  push, playbooks all live here.
- `cli/` `ro chat`, `ro up`/`down`, `ro doctor`, `ro export`,
  `ro playbooks`, `ro status`.
- `desktop/` menubar app: push-to-talk, conversation mode, screen sense,
  clipboard memory, pending approvals with quick approve/reject.
- `playbooks/` your saved playbooks (gitignored, yours).
- `bots/` your hired crew's charters (gitignored, yours).
- `infra/launchd/` service plists installed by `ro up`; `infra/systemd/`
  for an always-on linux substrate.

## quick start

you need: macos, homebrew, pnpm, node 20+, python 3.12, uv, docker desktop
(or brew postgres 17 + pgvector on port 5435).

```
git clone https://github.com/rohithkandula19/RohiRo && cd RohiRo
./scripts/bootstrap.sh
./scripts/go_live.sh
```

go_live walks you through everything interactively — keys into your
keychain, permissions with re-checking, services up — and ends with ro
introducing itself. `uv run ro doctor` any time shows every dependency as
a green check or a red line with its exact fix.

web ui at http://localhost:3000, api at http://localhost:8000. open the ui,
hit cmd-k, say hi.

### wiring the channels (each fails closed until configured)

```
keyring set ro imessage_channel     # your number/email or a chat name
keyring set ro telegram_owner_id    # your numeric telegram id
keyring set ro user_email           # your gmail address
```

grant full disk access (chat.db) and automation (Messages.app) to the
process running the api. `docs/runbook.md` covers every red light.

### always on

```
uv run ro up      # installs + loads launchd services
uv run ro down    # stops them
```

honest posture: best effort while the mac is awake. routines catch up on
wake instead of pretending to be a data center.

## entry points

- web: http://localhost:3000 (tailscale for your phone)
- imessage: text your ro channel
- telegram: message your bot
- cli: `ro chat`
- voice: ios shortcut posts audio to `/api/voice/talk`
- menubar: hotkey push-to-talk + approvals

## hard rules

- secrets live in macos keychain. never in `.env`. never committed.
- any action that touches another person or moves money requires your
  explicit ok. replying to you in your own channel does not.
- reads run automatically. writes to your own systems run automatically.
  writes outward wait for approval. playbooks cannot bypass the gate.
- channels fail closed: no owner configured, no listener.
- if a tool fails, the supervisor reports it. it never makes up tool output.

## docs

- `docs/runbook.md` what to do when something goes red
- `docs/deploy-substrate.md` true 24/7 on a mac mini or vps
- `docs/voice-shortcut.md` ios shortcut setup
- `docs/mobile-access.md` tailscale setup for phone
- `docs/demo.md` a 60 second walkthrough
- `docs/launch.md` the show hn kit
- `SECURITY.md` the load-bearing claims and how to verify each one
- `CONTRIBUTING.md` the non-negotiables
- `DECISIONS.md` every choice made along the way and why
- `PLAN.md` the reviewed build plan this version shipped from

## license

mit. it's yours now too.