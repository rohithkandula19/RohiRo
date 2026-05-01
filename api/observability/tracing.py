"""langfuse client. silent if not configured."""

from __future__ import annotations

import contextlib
from typing import Any, Iterator, Optional

from api.config import secrets, settings
from api.observability.logging import log


class _NoopLangfuse:
    def trace(self, **_: Any) -> Any:
        return self

    def span(self, **_: Any) -> Any:
        return self

    def generation(self, **_: Any) -> Any:
        return self

    def update(self, **_: Any) -> None:  # noqa: D401
        return None

    def end(self, **_: Any) -> None:
        return None

    def flush(self) -> None:
        return None


def _build() -> Any:
    pk = secrets.get("langfuse_public_key")
    sk = secrets.get("langfuse_secret_key")
    if not pk or not sk:
        return _NoopLangfuse()
    try:
        from langfuse import Langfuse  # type: ignore

        return Langfuse(public_key=pk, secret_key=sk, host=settings.langfuse_host)
    except Exception as e:
        log.warning("langfuse init failed, traces disabled", error=str(e))
        return _NoopLangfuse()


langfuse = _build()


@contextlib.contextmanager
def trace_span(name: str, **kwargs: Any) -> Iterator[Any]:
    """context-managed span. always closes, never raises into caller."""

    span: Optional[Any] = None
    try:
        span = langfuse.span(name=name, **kwargs)
        yield span
    finally:
        if span is not None:
            try:
                span.end()
            except Exception:
                pass
