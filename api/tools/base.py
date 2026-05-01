"""one tool abc across all tools.

every tool exposes: name, description, param_schema, requires_approval,
run(), mock_run(), retry policy. agents only see Tool.
"""

from __future__ import annotations

import abc
import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional


class ToolError(RuntimeError):
    pass


@dataclass
class RetryPolicy:
    attempts: int = 2
    base_delay_s: float = 0.5


@dataclass
class Tool(abc.ABC):
    name: str
    description: str
    param_schema: dict[str, Any]
    requires_approval: bool = False
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    mock_only: bool = False  # true when api keys missing or tier-2 disabled

    @abc.abstractmethod
    async def run(self, **params: Any) -> Any: ...

    async def mock_run(self, **params: Any) -> Any:
        return {"mocked": True, "tool": self.name, "params": params}

    async def call(self, **params: Any) -> Any:
        if self.mock_only:
            return await self.mock_run(**params)
        last: Optional[Exception] = None
        for i in range(self.retry.attempts + 1):
            try:
                return await self.run(**params)
            except Exception as e:  # noqa: BLE001
                last = e
                if i == self.retry.attempts:
                    raise ToolError(f"{self.name} failed: {e}") from e
                await asyncio.sleep(self.retry.base_delay_s * (2**i))
        raise ToolError(f"{self.name} exhausted retries: {last}")


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"no such tool: {name}")
        return self._tools[name]

    def all(self) -> list[Tool]:
        return list(self._tools.values())


registry = ToolRegistry()
