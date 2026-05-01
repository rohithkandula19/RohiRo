"""smoke tests. they don't hit anthropic or postgres, they only import."""

from __future__ import annotations


def test_app_imports() -> None:
    from api.main import app

    routes = {r.path for r in app.routes}
    assert "/health" in routes
    assert "/api/chat" in routes
    assert "/api/chat/stream" in routes
    assert "/api/memory/profile" in routes


def test_router_classifies_chat() -> None:
    # plain import test, doesn't call the model.
    from api.supervisor.router import DOMAINS

    assert "comms" in DOMAINS
    assert "memory" in DOMAINS
    assert "chat" in DOMAINS


def test_tool_base() -> None:
    from api.tools.base import Tool, ToolRegistry, RetryPolicy

    class T(Tool):
        async def run(self, **params):  # noqa: D401
            return "ok"

    reg = ToolRegistry()
    t = T(name="x", description="y", param_schema={}, retry=RetryPolicy())
    reg.register(t)
    assert reg.get("x") is t
