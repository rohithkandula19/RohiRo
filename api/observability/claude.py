"""one anthropic client wrapper.

handles: api key from keychain, retries on transient errors, token logging,
optional model fallback. agents only ever talk to this.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Optional

from anthropic import APIConnectionError, APIStatusError, AsyncAnthropic
from anthropic.types import Message

from api.config import secrets, settings
from api.observability.logging import log


@dataclass
class ClaudeUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_create_tokens: int = 0


class ClaudeClient:
    def __init__(self) -> None:
        self._client: Optional[AsyncAnthropic] = None
        self.total = ClaudeUsage()

    @property
    def client(self) -> AsyncAnthropic:
        if self._client is None:
            key = secrets.require("anthropic_api_key")
            self._client = AsyncAnthropic(api_key=key)
        return self._client

    async def message(
        self,
        *,
        model: Optional[str] = None,
        system: Optional[str] = None,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        retries: int = 2,
        fallback_model: Optional[str] = None,
    ) -> Message:
        chosen = model or settings.model_default
        attempt = 0
        last_err: Optional[Exception] = None
        while attempt <= retries:
            try:
                kwargs: dict[str, Any] = dict(
                    model=chosen,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=messages,
                )
                if system:
                    kwargs["system"] = system
                if tools:
                    kwargs["tools"] = tools
                resp = await self.client.messages.create(**kwargs)
                self._record_usage(resp)
                self._record_spend(resp, chosen)
                return resp
            except APIStatusError as e:
                last_err = e
                if e.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                    sleep_s = 0.5 * (2**attempt)
                    log.warning("claude transient error, retrying", status=e.status_code, sleep=sleep_s)
                    await asyncio.sleep(sleep_s)
                    attempt += 1
                    continue
                if fallback_model and chosen != fallback_model and attempt == retries:
                    log.warning("claude failing, falling back", to=fallback_model)
                    chosen = fallback_model
                    attempt = 0
                    continue
                raise
            except APIConnectionError as e:
                # network drops deserve the same retry policy as 5xx.
                last_err = e
                if attempt < retries:
                    sleep_s = 0.5 * (2**attempt)
                    log.warning("claude connection error, retrying", sleep=sleep_s)
                    await asyncio.sleep(sleep_s)
                    attempt += 1
                    continue
                raise
            except Exception as e:
                last_err = e
                raise
        raise RuntimeError(f"claude exhausted retries: {last_err}")

    def _record_usage(self, resp: Message) -> None:
        u = getattr(resp, "usage", None)
        if not u:
            return
        self.total.input_tokens += getattr(u, "input_tokens", 0) or 0
        self.total.output_tokens += getattr(u, "output_tokens", 0) or 0
        self.total.cache_read_tokens += getattr(u, "cache_read_input_tokens", 0) or 0
        self.total.cache_create_tokens += getattr(u, "cache_creation_input_tokens", 0) or 0

    def _record_spend(self, resp: Message, model: str) -> None:
        """persist per-call spend attributed to the current run. fire and
        forget: accounting never blocks or fails a model call."""
        u = getattr(resp, "usage", None)
        if not u:
            return
        try:
            from api.observability import budget
            asyncio.get_running_loop().create_task(budget.record_usage(
                model=model,
                input_tokens=getattr(u, "input_tokens", 0) or 0,
                output_tokens=getattr(u, "output_tokens", 0) or 0,
            ))
        except Exception:
            pass


claude_client = ClaudeClient()
