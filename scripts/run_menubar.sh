#!/usr/bin/env bash
# launch the ro menubar app. assumes you're in the repo root.
# rumps requires a real macos session (not a daemon), so this is meant for
# launchd as a LaunchAgent (per-user), not LaunchDaemon (root).
set -euo pipefail

cd "$(dirname "$0")/.."
export RO_API_BASE="${RO_API_BASE:-http://127.0.0.1:8000}"
export RO_HOTKEY="${RO_HOTKEY:-<alt>+<space>}"
exec uv run python desktop/menubar.py
