#!/usr/bin/env bash
# walks through every api key ro needs.
# stores them in macos keychain via the 'ro' service.
# never writes to disk. you can re-run this and skip what's already there.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

exec uv run python scripts/setup_keys.py "$@"
