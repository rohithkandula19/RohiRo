"""one-time gmail oauth setup.

run this once. it opens a browser, you grant ro access to your gmail, and
the token is written to ~/.config/ro/gmail_token.json. ro reads from there.

prerequisites:
1. go to https://console.cloud.google.com/
2. create or pick a project
3. enable the gmail api
4. credentials → create credentials → oauth client id → desktop app
5. download the json. save it to ~/.config/ro/gmail_client.json

then run:  python scripts/setup_gmail_oauth.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
]

CLIENT_PATH = Path.home() / ".config" / "ro" / "gmail_client.json"
TOKEN_PATH = Path.home() / ".config" / "ro" / "gmail_token.json"


def main() -> int:
    if not CLIENT_PATH.exists():
        print(f"missing {CLIENT_PATH}")
        print()
        print("create an oauth client id in google cloud console:")
        print("  1. https://console.cloud.google.com/")
        print("  2. enable the gmail api")
        print("  3. credentials → create credentials → oauth client id → desktop app")
        print(f"  4. download the json, save it to {CLIENT_PATH}")
        print()
        return 1

    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_PATH), SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True)
    TOKEN_PATH.write_text(creds.to_json())
    print(f"ok. token saved to {TOKEN_PATH}")
    print("you can now ask ro to read your inbox.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
