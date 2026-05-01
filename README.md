# ro

a personal agent operating system. one user. local first. runs on your mac.

ro reads your email, knows your calendar, watches your repos, drafts your replies, and asks before sending anything. it lives on your laptop, runs on your terms, forgets nothing.

## what's in here

a turborepo monorepo with two main pieces.

- `web/` is the next.js 14 ui you talk to in the browser. all 11 pages and a settings page, every domain on its own route.
- `api/` is a fastapi server that runs the supervisor and 11 sub-agents in langgraph. it does the actual work.

plus a memory layer in postgres + pgvector, redis for session state, langfuse for traces, and a handful of entry points (cli, imessage, telegram, voice) so you can reach ro from wherever you are.

## quick start

you need: macos, homebrew, pnpm, node 20+, python 3.12, uv, docker desktop.

```
./scripts/bootstrap.sh
./scripts/setup_keys.sh
pnpm dev
```

that brings up the web ui at http://localhost:3000 and the api at http://localhost:8000. open the ui, hit cmd-k, say hi.

## entry points

- web: http://localhost:3000 (and via tailscale on your phone)
- cli: `ro chat`
- imessage: send to your own number, the listener daemon forwards
- telegram: configure in `/settings`, message your bot
- voice: ios shortcut posts audio to `/api/voice`

## hard rules

- secrets live in macos keychain. never in `.env`. never committed.
- any action that touches another person or moves money requires your explicit ok in the chat.
- reads run automatically. writes to your own systems run automatically. writes outward wait for approval.
- if a tool fails, the supervisor reports it. it never makes up tool output.

## docs

- `docs/voice-shortcut.md` how to set up the ios shortcut
- `docs/mobile-access.md` tailscale setup for phone
- `docs/demo.md` a 60 second walkthrough
- `DECISIONS.md` every choice made along the way and why

## license

private. for ro.
