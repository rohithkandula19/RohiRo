#!/usr/bin/env bash
# bootstrap ro on a fresh mac.
# safe to run more than once. it skips what's already there.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

say() { printf "\033[1;32m==> %s\033[0m\n" "$*"; }
warn() { printf "\033[1;33m==> %s\033[0m\n" "$*"; }
fail() { printf "\033[1;31m==> %s\033[0m\n" "$*"; exit 1; }

[[ "$(uname)" == "Darwin" ]] || fail "this is a mac-only setup"

say "checking homebrew"
if ! command -v brew >/dev/null 2>&1; then
    fail "install homebrew first: https://brew.sh"
fi

say "checking required tools"
for cmd in node pnpm python3 uv docker; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        warn "$cmd missing"
        case "$cmd" in
            node) brew install node@20 ;;
            pnpm) brew install pnpm ;;
            uv) brew install uv ;;
            docker) warn "install docker desktop from https://docker.com/products/docker-desktop" ;;
        esac
    fi
done

say "installing node deps"
pnpm install

say "installing python deps with uv"
uv sync --dev

say "starting local stack (postgres, redis, langfuse)"
docker compose up -d postgres redis

say "waiting for postgres to be ready"
for i in {1..30}; do
    if docker exec ro-postgres pg_isready -U ro >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

say "applying memory schema"
docker exec -i ro-postgres psql -U ro -d ro < api/memory/schema.sql >/dev/null

say "starting langfuse for traces"
docker compose up -d langfuse-db langfuse || warn "langfuse failed to start, traces will be off"

say "all set. next steps:"
echo "  1. ./scripts/setup_keys.sh  (configure api keys in keychain)"
echo "  2. uv run python scripts/seed_profile.py  (set up your profile)"
echo "  3. pnpm dev  (boot the web ui and api)"
