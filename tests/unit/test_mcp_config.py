"""mcp config parsing and keychain env resolution."""

from __future__ import annotations

import json
from unittest.mock import patch

from api.integrations import mcp_host


def test_missing_config_is_empty(tmp_path) -> None:
    with patch.object(mcp_host, "CONFIG_PATH", tmp_path / "nope.json"):
        assert mcp_host.load_config() == {}
        assert not mcp_host.configured()


def test_config_parses_and_filters(tmp_path) -> None:
    p = tmp_path / "mcp_servers.json"
    p.write_text(json.dumps({
        "mcpServers": {
            "fs": {"command": "npx", "args": ["-y", "server-fs"], "env": {}},
            "broken": {"args": ["no-command"]},
        }
    }))
    with patch.object(mcp_host, "CONFIG_PATH", p):
        cfg = mcp_host.load_config()
        assert "fs" in cfg and "broken" not in cfg
        assert cfg["fs"]["command"] == "npx"


def test_keychain_env_resolution() -> None:
    with patch.object(mcp_host.secrets, "get", side_effect=lambda k, d=None: "tok" if k == "gh" else None):
        resolved = mcp_host._resolve_env({
            "TOKEN": "keychain:gh",
            "MISSING": "keychain:absent",
            "PLAIN": "value",
        })
        assert resolved == {"TOKEN": "tok", "PLAIN": "value"}


def test_compact_tool_list() -> None:
    tools = {
        "fs": {"ok": True, "tools": [{"name": "read_file", "description": "read a file"}]},
        "down": {"ok": False, "error": "spawn failed"},
    }
    listing = mcp_host.compact_tool_list(tools)
    assert "fs:read_file" in listing
    assert "down" not in listing
