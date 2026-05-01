#!/usr/bin/env bash
# nightly backup. dumps postgres, encrypts with age, ships to gcs.
# safe to run any time. exits 0 if there's nothing to do.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="$ROOT/backups"
mkdir -p "$OUT_DIR"

DUMP="$OUT_DIR/ro-$STAMP.sql.gz"
docker exec ro-postgres pg_dump -U ro -d ro | gzip > "$DUMP"

RECIPIENT="$(uv run python -c "import keyring; print(keyring.get_password('ro', 'backup_age_recipient') or '')")"
if [[ -z "$RECIPIENT" ]]; then
    echo "no backup_age_recipient in keychain, leaving local-only at $DUMP"
    exit 0
fi

if ! command -v age >/dev/null; then
    echo "age not installed (brew install age). leaving local-only at $DUMP"
    exit 0
fi

ENC="$DUMP.age"
age -r "$RECIPIENT" -o "$ENC" "$DUMP"
rm "$DUMP"

BUCKET="$(uv run python -c "import keyring; print(keyring.get_password('ro', 'gcs_bucket') or '')")"
if [[ -z "$BUCKET" ]]; then
    echo "no gcs_bucket in keychain, leaving encrypted local-only at $ENC"
    exit 0
fi

if command -v gcloud >/dev/null; then
    gsutil cp "$ENC" "gs://$BUCKET/ro/$(basename "$ENC")"
    rm "$ENC"
else
    echo "gcloud not installed, encrypted backup is at $ENC"
fi
