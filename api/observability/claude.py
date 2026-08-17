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
        # lane enforcement: vault content and airgap mode never reach the api.
        # this is the choke point — the check runs before any bytes leave.
        from api.observability import lanes
        await lanes.check_cloud("claude")

        chosen = model or settings.model_default

        # no anthropic key but an openrouter key: same claude models through
        # openrouter's gateway. tools are not supported on this path yet, so
        # tool-bearing calls still require the direct key.
        if not secrets.get("anthropic_api_key") and secrets.get("openrouter_api_key"):
            if tools:
                raise RuntimeError(
                    "tool calls need a direct anthropic_api_key; openrouter path is text-only for now"
                )
            resp = await _openrouter_message(
                model=chosen, system=system, messages=messages,
                max_tokens=max_tokens, temperature=temperature,
            )
            self._record_usage(resp)
            self._record_spend(resp, f"openrouter:{_openrouter_model(chosen)}")
            return resp

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


def configured() -> bool:
    """is a brain available? anthropic direct, or anthropic-via-openrouter.
    background loops gate on this so a keyless install stays quiet instead
    of tracebacking every interval."""
    return bool(secrets.get("anthropic_api_key")) or bool(secrets.get("openrouter_api_key"))


# ----- openrouter path (anthropic models through the openai-compatible api) -----
#
# store the key yourself (never paste keys into chats):
#   uv run python -c "import keyring; keyring.set_password('ro','openrouter_api_key', input('key: '))"
# optional: pin one model for everything:
#   keychain key openrouter_model, e.g. anthropic/claude-sonnet-4.5


class _ShimBlock:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class _ShimUsage:
    def __init__(self, prompt: int, completion: int) -> None:
        self.input_tokens = prompt
        self.output_tokens = completion
        self.cache_read_input_tokens = 0
        self.cache_creation_input_tokens = 0


class _ShimMessage:
    """quacks like anthropic.types.Message for every caller in this repo
    (content blocks with .type/.text, and .usage token counts)."""

    def __init__(self, text: str, prompt: int, completion: int) -> None:
        self.content = [_ShimBlock(text)]
        self.usage = _ShimUsage(prompt, completion)


def _openrouter_model(requested: str) -> str:
    pinned = secrets.get("openrouter_model")
    if pinned:
        return pinned
    # claude-sonnet-4-6 -> anthropic/claude-sonnet-4-6; already-prefixed passes through
    return requested if "/" in requested else f"anthropic/{requested}"


async def _openrouter_message(
    *,
    model: str,
    system: Optional[str],
    messages: list[dict[str, Any]],
    max_tokens: int,
    temperature: float,
) -> Message:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=secrets.get("openrouter_api_key"),
    )
    oai_messages: list[dict[str, Any]] = []
    if system:
        oai_messages.append({"role": "system", "content": system})
    oai_messages += messages
    resp = await client.chat.completions.create(
        model=_openrouter_model(model),
        messages=oai_messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    text = (resp.choices[0].message.content or "") if resp.choices else ""
    usage = getattr(resp, "usage", None)
    return _ShimMessage(  # type: ignore[return-value]
        text,
        getattr(usage, "prompt_tokens", 0) or 0,
        getattr(usage, "completion_tokens", 0) or 0,
    )


claude_client = ClaudeClient()
