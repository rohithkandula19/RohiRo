"""interactive walk-through of every key ro needs.

stores values in macos keychain under the 'ro' service.
never writes secrets to disk. safe to re-run.
"""

from __future__ import annotations

import getpass
import sys

import keyring

SERVICE = "ro"

# (key_name, label, required)
KEYS: list[tuple[str, str, bool]] = [
    ("anthropic_api_key", "anthropic api key (claude)", True),
    ("openai_api_key", "openai api key (embeddings only)", True),
    ("langfuse_public_key", "langfuse public key", False),
    ("langfuse_secret_key", "langfuse secret key", False),
    ("postgres_url", "postgres connection url", True),
    ("redis_url", "redis connection url", True),
    # gmail / calendar / drive use oauth, no static keys here.
    ("github_token", "github personal access token", False),
    ("slack_bot_token", "slack bot token (xoxb-...)", False),
    ("slack_app_token", "slack app-level token (xapp-...)", False),
    ("notion_token", "notion integration token", False),
    ("linear_api_key", "linear api key", False),
    ("plaid_client_id", "plaid client id", False),
    ("plaid_secret", "plaid secret (sandbox or development)", False),
    ("plaid_env", "plaid environment (sandbox / development / production)", False),
    ("telegram_bot_token", "telegram bot token", False),
    ("telegram_owner_id", "your telegram chat id (so the bot only talks to you)", False),
    ("strava_client_id", "strava client id", False),
    ("strava_client_secret", "strava client secret", False),
    ("gcs_bucket", "gcs bucket for nightly backups", False),
    ("backup_age_recipient", "age public key for backup encryption", False),
    ("vapid_public_key", "vapid public key for web push", False),
    ("vapid_private_key", "vapid private key for web push", False),
]

DEFAULTS = {
    "postgres_url": "postgresql://ro:ro_local_dev@localhost:5432/ro",
    "redis_url": "redis://localhost:6379/0",
    "langfuse_public_key": "pk-lf-ro-local",
    "langfuse_secret_key": "sk-lf-ro-local",
    "plaid_env": "sandbox",
}


def main() -> int:
    print()
    print("setting up keys for ro.")
    print("each value goes into macos keychain under service 'ro'.")
    print("press enter to skip optional ones. type 'rotate' to overwrite an existing key.")
    print()

    for name, label, required in KEYS:
        existing = keyring.get_password(SERVICE, name)
        suffix = ""
        if existing:
            tail = existing[-4:] if len(existing) > 4 else "****"
            suffix = f" (set, ends ...{tail})"
        prompt = f"{label}{suffix}: "
        try:
            if existing:
                value = input(prompt).strip()
                if not value:
                    continue
                if value.lower() == "rotate":
                    value = getpass.getpass(f"new value for {name}: ").strip()
                    if not value:
                        continue
            else:
                default = DEFAULTS.get(name)
                if default:
                    value = input(f"{prompt}[{default}] ").strip() or default
                elif "secret" in name or "token" in name or "key" in name:
                    value = getpass.getpass(prompt).strip()
                else:
                    value = input(prompt).strip()

            if not value:
                if required:
                    print(f"  required, leaving blank for now. set later with: keyring set ro {name}")
                continue

            keyring.set_password(SERVICE, name, value)
            print(f"  saved {name}")
        except KeyboardInterrupt:
            print()
            return 1

    print()
    print("done. run pnpm dev to boot.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
