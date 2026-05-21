"""Tests for the Dolphi MCP server tool surface.

We exercise the underlying handler coroutines directly (rather than going
through stdio) so the tests are fast, hermetic, and don't require the MCP
client transport. ``mock=True`` keeps everything offline.
"""

from __future__ import annotations

import asyncio
import json

import pytest

mcp_server = pytest.importorskip("dolphi.mcp_server")


def _list_tools() -> list:
    return asyncio.run(mcp_server._list_tools())


def _call_tool(name: str, arguments: dict) -> list:
    return asyncio.run(mcp_server._call_tool(name, arguments))


def test_server_lists_4_tools() -> None:
    tools = _list_tools()
    names = {t.name for t in tools}
    assert names == {
        "dolphi_evaluate",
        "dolphi_check_falsifiers",
        "dolphi_list_falsifiers",
        "dolphi_get_decision_log",
    }
    # Every tool must have a non-empty description and an object schema.
    for tool in tools:
        assert tool.description
        assert tool.inputSchema["type"] == "object"


def test_evaluate_tool_returns_valid_json() -> None:
    result = _call_tool("dolphi_evaluate", {"symbols": ["NVDA"], "mock": True})
    assert len(result) == 1
    content = result[0]
    assert content.type == "text"
    payload = json.loads(content.text)
    # EvaluateResult shape — see dolphi/api.py.
    for key in ("ranked_ideas", "falsifiers", "fragility", "debate", "allocations", "decision_id"):
        assert key in payload, f"missing key {key!r} in evaluate result"


def test_unknown_tool_raises() -> None:
    with pytest.raises(ValueError, match="Unknown tool"):
        _call_tool("dolphi_does_not_exist", {})
