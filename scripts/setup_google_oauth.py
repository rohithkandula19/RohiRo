"""one-time google oauth setup.

opens a browser, you grant ro access to gmail + calendar + drive, and the
token is written to ~/.config/ro/google_token.json. all google integrations
read from there.

prerequisites:
1. https://console.cloud.google.com/
2. create or pick a project
3. enable: gmail api, google calendar api, google drive api
4. credentials → create credentials → oauth client id → desktop app
5. download the json, save it to ~/.config/ro/google_client.json

then run:  uv run python scripts/setup_google_oauth.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    # gmail
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    # calendar
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    # drive (read-only; used by /files later)
    "https://www.googleapis.com/auth/drive.readonly",
]

CLIENT_PATH = Path.home() / ".config" / "ro" / "google_client.json"
TOKEN_PATH = Path.home() / ".config" / "ro" / "google_token.json"


def main() -> int:
    if not CLIENT_PATH.exists():
        print(f"missing {CLIENT_PATH}")
        print()
        print("create an oauth client id:")
        print("  1. https://console.cloud.google.com/")
        print("  2. enable gmail api, google calendar api, google drive api")
        print("  3. credentials → create credentials → oauth client id → desktop app")
        print(f"  4. download the json, save it to {CLIENT_PATH}")
        return 1

    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_PATH), SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True)
    TOKEN_PATH.write_text(creds.to_json())
    print(f"ok. token saved to {TOKEN_PATH}")
    print("ro can now read gmail, calendar, and drive.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
