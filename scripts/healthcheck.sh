#!/usr/bin/env bash
# quick health check. prints status of each piece.

set -uo pipefail

ok() { printf "  \033[32m✓\033[0m %s\n" "$*"; }
bad() { printf "  \033[31m✗\033[0m %s\n" "$*"; }

echo "ro health check"

if curl -sf http://localhost:8000/health >/dev/null 2>&1; then ok "api"; else bad "api (localhost:8000)"; fi
if curl -sf http://localhost:3000 >/dev/null 2>&1; then ok "web"; else bad "web (localhost:3000)"; fi
if docker exec ro-postgres pg_isready -U ro >/dev/null 2>&1; then ok "postgres"; else bad "postgres"; fi
if docker exec ro-redis redis-cli ping >/dev/null 2>&1; then ok "redis"; else bad "redis"; fi
if curl -sf http://localhost:3030/api/public/health >/dev/null 2>&1; then ok "langfuse"; else bad "langfuse (optional)"; fi
