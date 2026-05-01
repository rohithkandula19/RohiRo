"""runtime config for the api.

settings: non-secret values (urls, model defaults, feature flags).
secrets: thin keychain wrapper. raises a clear error if a key is missing.
"""

from __future__ import annotations

import logging
from functools import cached_property
from typing import Optional

import keyring
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)

KEYCHAIN_SERVICE = "ro"


class _MissingKey(RuntimeError):
    pass


class Secrets:
    """fetch a secret from macos keychain.

    if a key is missing, returns None for the default getters and raises
    for `require`. lets startup come up with stubs for unconfigured tools.
    """

    def get(self, name: str, default: Optional[str] = None) -> Optional[str]:
        try:
            value = keyring.get_password(KEYCHAIN_SERVICE, name)
        except Exception as e:
            log.warning("keychain read failed for %s: %s", name, e)
            return default
        if value is None:
            return default
        return value

    def require(self, name: str) -> str:
        value = self.get(name)
        if not value:
            raise _MissingKey(
                f"missing key '{name}' in keychain. run scripts/setup_keys.sh"
            )
        return value


secrets = Secrets()


class Settings(BaseSettings):
    """non-secret settings. defaults are local dev."""

    env: str = Field(default="dev")
    api_host: str = Field(default="127.0.0.1")
    api_port: int = Field(default=8000)
    web_origin: str = Field(default="http://localhost:3000")

    # models. defaults match the build spec: sonnet default, opus hard, haiku classifier.
    # using the latest sonnet (4.6) since 4.5 retired before this build. logged in DECISIONS.md.
    model_default: str = Field(default="claude-sonnet-4-6")
    model_hard: str = Field(default="claude-opus-4-7")
    model_cheap: str = Field(default="claude-haiku-4-5-20251001")
    model_embed: str = Field(default="text-embedding-3-small")

    # behavior
    max_tool_turns: int = Field(default=8)
    chat_stream_heartbeat_s: float = Field(default=15.0)

    # observability
    langfuse_host: str = Field(default="http://localhost:3030")

    model_config = SettingsConfigDict(env_prefix="RO_", env_file=None, extra="ignore")

    @cached_property
    def postgres_url(self) -> str:
        return secrets.get("postgres_url") or "postgresql://ro:ro_local_dev@localhost:5432/ro"

    @cached_property
    def redis_url(self) -> str:
        return secrets.get("redis_url") or "redis://localhost:6379/0"


settings = Settings()
