#!/bin/zsh
# go live. one command, guided, verified at every step.
#   ./scripts/go_live.sh
set -e
cd "$(dirname "$0")/.."

say()  { print -P "%F{cyan}▸%f $1"; }
ok()   { print -P "%F{green}✓%f $1"; }
bad()  { print -P "%F{red}✗%f $1"; }
ask()  { print -Pn "%F{yellow}?%f $1 "; }

print -P "%B── ro go-live ──%b"
echo "this walks you through every step and checks each one. ctrl-c anytime; rerun resumes."
echo

# ── 1. database ──────────────────────────────────────────────────────
say "checking postgres + redis"
if pg_isready -h localhost -p 5435 >/dev/null 2>&1; then
  ok "postgres answering on 5435"
elif docker compose ps 2>/dev/null | grep -q ro-postgres; then
  ok "docker stack running"
else
  say "starting brew services (postgresql@17 on 5435 + redis)"
  brew services start postgresql@17 >/dev/null 2>&1 || true
  brew services start redis >/dev/null 2>&1 || true
  sleep 3
  pg_isready -h localhost -p 5435 >/dev/null 2>&1 && ok "postgres up" || {
    bad "postgres not answering on 5435. start docker desktop and run: docker compose up -d"
    exit 1
  }
fi
PGBIN=$(ls -d /opt/homebrew/opt/postgresql@1*/bin 2>/dev/null | tail -1)
if [ -n "$PGBIN" ] && $PGBIN/psql -p 5435 -U ro -d ro -h localhost -tc "select 1" >/dev/null 2>&1; then
  $PGBIN/psql -p 5435 -U ro -d ro -h localhost -f api/memory/schema.sql >/dev/null 2>&1 || true
  $PGBIN/psql -p 5435 -U ro -d ro -h localhost -f api/memory/tree_schema.sql >/dev/null 2>&1 || true
  ok "schema applied"
fi

# ── 2. keys ──────────────────────────────────────────────────────────
_key() {  # _key <name> <prompt> <required> [default]
  local name=$1 prompt=$2 required=$3 default=${4:-}
  local existing
  existing=$(uv run python -c "import keyring; print(keyring.get_password('ro','$name') or '')" 2>/dev/null)
  if [ -n "$existing" ]; then ok "$name already set"; return; fi
  while true; do
    if [ -n "$default" ]; then ask "$prompt [$default]:"; else ask "$prompt:"; fi
    read -r value
    [ -z "$value" ] && value=$default
    if [ -z "$value" ]; then
      if [ "$required" = "yes" ]; then bad "required — ro has no brain without it"; continue
      else say "skipped $name (add later with scripts/setup_keys.sh)"; return; fi
    fi
    uv run python -c "import keyring; keyring.set_password('ro','$name','''$value''')"
    ok "$name saved to keychain"
    return
  done
}

echo
say "keys go into the macos keychain, never into files."
echo "  get your anthropic key at: https://console.anthropic.com/settings/keys"
_key anthropic_api_key "anthropic api key (sk-ant-…)" yes
_key imessage_channel  "your own phone number or apple id email (the ro channel)" no
_key user_email        "your gmail address" no
_key telegram_bot_token "telegram bot token from @BotFather (optional)" no
_key telegram_owner_id  "your numeric telegram id (optional, from @userinfobot)" no

# ── 3. push keys ─────────────────────────────────────────────────────
echo
if uv run python -c "import keyring,sys; sys.exit(0 if keyring.get_password('ro','vapid_private_key') else 1)" 2>/dev/null; then
  ok "web push keys exist"
else
  say "generating web push keys"
  uv run python -m api.integrations.webpush --generate >/dev/null 2>&1 && ok "push keys saved" || say "push keygen skipped (fine)"
fi

# ── 4. mac permissions ───────────────────────────────────────────────
echo
say "checking full disk access (chat.db)"
while true; do
  if uv run python -c "
from api.integrations import imessage
import sys; sys.exit(0 if imessage.configured() else 1)" 2>/dev/null; then
    ok "chat.db readable — imessage channel will work"
    break
  fi
  bad "chat.db not readable yet."
  echo "   open: System Settings → Privacy & Security → Full Disk Access"
  echo "   add + enable your terminal app (Terminal or iTerm), then RESTART the terminal if asked."
  ask "press enter to re-check (or type skip):"; read -r again
  [ "$again" = "skip" ] && { say "skipped — imessage stays off until granted"; break; }
done
echo "note: the first imessage SEND will pop an Automation permission dialog — click ok when it does."

# ── 5. bring it up ───────────────────────────────────────────────────
echo
say "starting services (launchd: api, web, jobs)"
uv run ro up || true
sleep 6
if curl -s http://127.0.0.1:8000/health | grep -q ok; then
  ok "api healthy"
else
  bad "api not answering yet — check: tail -50 /tmp/ro.api.log"; exit 1
fi

# ── 6. first real thought ────────────────────────────────────────────
echo
say "asking ro its first question through the full supervisor…"
REPLY=$(curl -s -X POST http://127.0.0.1:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"text":"introduce yourself in two sentences. mention one thing you can do."}' | \
  uv run python -c "import json,sys; print(json.load(sys.stdin).get('text','(no reply)'))" 2>/dev/null)
echo
print -P "%F{magenta}ro says:%f $REPLY"
echo
ok "ro is alive."
echo "  • web ui:      http://localhost:3000"
echo "  • text your own number — the ro channel answers"
echo "  • morning digest arrives via ro.digest.plist"
echo "  • /audit shows the receipt of everything it ever sends"
