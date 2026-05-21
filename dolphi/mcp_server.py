"""Dolphi MCP server — exposes the dolphi.api facade as MCP tools.

This server runs over stdio and is meant to be wired into Claude Desktop,
Cursor, or any other MCP-compatible agent harness. It exposes four tools
that thinly wrap the sync functions in :mod:`dolphi.api`.

Because the rest of dolphi is 100% sync but MCP transport is async, every
tool call is dispatched through ``asyncio.to_thread`` so a slow LLM call
inside ``evaluate()`` does not block the stdio event loop.

Run with ``dolphi-mcp`` (entry point installed by ``pip install dolphi[mcp]``)
or ``python -m dolphi.mcp_server``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from dolphi.api import (
    check_falsifiers,
    evaluate,
    get_decision_log,
    list_falsifiers,
)

logger = logging.getLogger("dolphi.mcp")

server: Server = Server("dolphi")


# ---------- tool catalog -----------------------------------------------------


_EVALUATE_DESCRIPTION = (
    "Run the full Dolphi multi-agent research workflow. Returns ranked ideas, "
    "per-symbol falsifiers, fragility scores, debate verdicts, and a portfolio "
    "allocation. Set mock=true for an offline deterministic run (no API keys)."
)

_CHECK_DESCRIPTION = (
    "Apply weekly falsifier-check feedback to a stored decision and return the "
    "computed position adjustments. Feedback keys are '{symbol}-{index}', values "
    "are 'safe' | 'triggered' | 'unsure'."
)

_LIST_DESCRIPTION = (
    "List falsifiers from a stored decision, keyed by symbol. Each falsifier's "
    "0-based index within its symbol's list is the value to pass back via "
    "dolphi_check_falsifiers."
)

_LOG_DESCRIPTION = (
    "Return up to `limit` most recent decision-log records (newest last) from "
    "~/.dolphi/decision_log.jsonl."
)


@server.list_tools()
async def _list_tools() -> list[Tool]:
    """Advertise the four Dolphi tools."""
    return [
        Tool(
            name="dolphi_evaluate",
            description=_EVALUATE_DESCRIPTION,
            inputSchema={
                "type": "object",
                "properties": {
                    "symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Seed symbols (e.g. ['NVDA','MSFT']). Omit for full discovery.",
                    },
                    "profile": {
                        "type": "object",
                        "description": "UserProfile fields (total_savings, risk_tolerance, ...).",
                    },
                    "top_k": {
                        "type": "integer",
                        "default": 5,
                        "description": "Number of ranked ideas to keep.",
                    },
                    "mock": {
                        "type": "boolean",
                        "default": False,
                        "description": "Offline deterministic run — no LLM, no network.",
                    },
                },
            },
        ),
        Tool(
            name="dolphi_check_falsifiers",
            description=_CHECK_DESCRIPTION,
            inputSchema={
                "type": "object",
                "properties": {
                    "feedback": {
                        "type": "object",
                        "description": "Map of '{symbol}-{index}' to 'safe' | 'triggered' | 'unsure'.",
                        "additionalProperties": {
                            "type": "string",
                            "enum": ["safe", "triggered", "unsure"],
                        },
                    },
                    "decision_id": {
                        "type": "string",
                        "description": "Decision timestamp; defaults to most recent.",
                    },
                },
                "required": ["feedback"],
            },
        ),
        Tool(
            name="dolphi_list_falsifiers",
            description=_LIST_DESCRIPTION,
            inputSchema={
                "type": "object",
                "properties": {
                    "decision_id": {
                        "type": "string",
                        "description": "Decision timestamp; defaults to most recent.",
                    },
                },
            },
        ),
        Tool(
            name="dolphi_get_decision_log",
            description=_LOG_DESCRIPTION,
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "default": 10,
                        "description": "Maximum number of records to return.",
                    },
                },
            },
        ),
    ]


# ---------- tool dispatch ----------------------------------------------------


@server.call_tool()
async def _call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Dispatch an MCP tool call to the underlying sync function."""
    arguments = arguments or {}
    logger.info("tool=%s args=%s", name, sorted(arguments.keys()))

    if name == "dolphi_evaluate":
        result = await asyncio.to_thread(evaluate, **arguments)
        return [TextContent(type="text", text=result.model_dump_json())]

    if name == "dolphi_check_falsifiers":
        result = await asyncio.to_thread(check_falsifiers, **arguments)
        return [TextContent(type="text", text=result.model_dump_json())]

    if name == "dolphi_list_falsifiers":
        result = await asyncio.to_thread(list_falsifiers, **arguments)
        payload = {sym: [f.model_dump() for f in fs] for sym, fs in result.items()}
        return [TextContent(type="text", text=json.dumps(payload))]

    if name == "dolphi_get_decision_log":
        result = await asyncio.to_thread(get_decision_log, **arguments)
        return [TextContent(type="text", text=json.dumps(result, default=str))]

    raise ValueError(f"Unknown tool: {name}")


# ---------- entry point ------------------------------------------------------


async def _run() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    """Console-script entry point for ``dolphi-mcp``."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    asyncio.run(_run())


if __name__ == "__main__":
    main()
