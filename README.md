> **⚠️ All Rights Reserved.** This repository is published for viewing and portfolio purposes only. The code is **not** open source — reuse, redistribution, modification, or derivative works are not permitted without written permission. See [LICENSE](./LICENSE).
# ro

a personal agent operating system. one user. local first. runs on your mac.

ro reads your email, knows your calendar, watches your repos, drafts your
replies, and asks before sending anything. text it from your phone, teach it
playbooks, let it run routines while you sleep. it lives on your laptop,
runs on your terms, forgets nothing, and never moves money or messages
without your yes.

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

## what's in here

a turborepo monorepo.

- `web/` next.js 14 ui. every domain a route, plus playbooks and settings
  (liveness, spend, push).
- `api/` fastapi + langgraph supervisor and sub-agents. listeners run
  in-process: imessage, telegram, gmail. scheduler, budget, heartbeats,
  push, playbooks all live here.
- `cli/` `ro chat`, `ro up`, `ro down`, `ro status`, `ro playbooks`.
- `desktop/` menubar app: talk to ro, pending approvals with quick
  approve/reject.
- `playbooks/` your saved playbooks (gitignored, yours).
- `infra/launchd/` service plists installed by `ro up`.

## quick start

you need: macos, homebrew, pnpm, node 20+, python 3.12, uv, docker desktop.

```
./scripts/bootstrap.sh
./scripts/setup_keys.sh
pnpm dev
```

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
- `docs/voice-shortcut.md` ios shortcut setup
- `docs/mobile-access.md` tailscale setup for phone
- `docs/demo.md` a 60 second walkthrough
- `DECISIONS.md` every choice made along the way and why
- `PLAN.md` the reviewed build plan this version shipped from

## license

private. for ro.
