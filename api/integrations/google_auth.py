"""shared google oauth credentials.

every google integration (gmail, calendar, drive) reads the same token file
written by scripts/setup_google_oauth.py. one auth, multiple apis.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

TOKEN_PATH = Path.home() / ".config" / "ro" / "google_token.json"
# back-compat for users who ran the older gmail-only setup
LEGACY_TOKEN_PATH = Path.home() / ".config" / "ro" / "gmail_token.json"

ALL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/drive.readonly",
]


def token_path() -> Path | None:
    if TOKEN_PATH.exists():
        return TOKEN_PATH
    if LEGACY_TOKEN_PATH.exists():
        return LEGACY_TOKEN_PATH
    return None


def configured() -> bool:
    return token_path() is not None


def _creds():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    path = token_path()
    if path is None:
        raise RuntimeError(
            "google account not connected. run `uv run python scripts/setup_google_oauth.py`."
        )
    creds = Credentials.from_authorized_user_file(str(path), ALL_SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            path.write_text(creds.to_json())
        else:
            raise RuntimeError("google token invalid; re-run setup_google_oauth.py")
    return creds


@lru_cache(maxsize=4)
def service(api: str, version: str):
    """build a google api client. cached so repeated calls reuse the client."""
    from googleapiclient.discovery import build

    return build(api, version, credentials=_creds(), cache_discovery=False)
