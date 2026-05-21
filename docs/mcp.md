# Dolphi MCP server

Dolphi ships an [MCP (Model Context Protocol)](https://modelcontextprotocol.io)
server so any MCP-compatible agent — Claude Desktop, Cursor, or your own
client — can call the same research pipeline that powers the `dolphi` CLI.
The server runs locally over stdio, has no network listener of its own, and
needs no auth.

## Install

```bash
pip install "dolphi[mcp]"
```

This installs the `mcp` Python SDK and registers a `dolphi-mcp` console
script. Verify with:

```bash
which dolphi-mcp
```

## Wire it into Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows) and add
Dolphi under `mcpServers`:

```json
{
  "mcpServers": {
    "dolphi": {
      "command": "dolphi-mcp"
    }
  }
}
```

Then fully quit and reopen Claude Desktop. Dolphi's four tools should show
up in the tools palette.

## Wire it into Cursor

Edit `~/.cursor/mcp.json` (create it if missing):

```json
{
  "mcpServers": {
    "dolphi": {
      "command": "dolphi-mcp"
    }
  }
}
```

Reload Cursor's MCP servers from Settings → MCP.

## The four tools

| Tool | What it does |
|---|---|
| `dolphi_evaluate` | Run the full multi-agent workflow; pass `mock: true` for an offline deterministic run. |
| `dolphi_check_falsifiers` | Apply weekly safe / triggered / unsure feedback to a stored decision. |
| `dolphi_list_falsifiers` | List falsifiers from a stored decision, keyed by symbol. |
| `dolphi_get_decision_log` | Return the most recent records from `~/.dolphi/decision_log.jsonl`. |

## Calling from your own agent

The server speaks JSON-RPC 2.0 over stdio. A `tools/call` request looks
like:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "dolphi_evaluate",
    "arguments": {"symbols": ["NVDA"], "mock": true}
  }
}
```

Use the official `mcp` Python SDK or the
[TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk)
for a real client; rolling your own JSON-RPC framing on top of stdio works
too.

## Troubleshooting

- **`dolphi-mcp: command not found`** — install with the extra:
  `pip install "dolphi[mcp]"`. The plain `pip install dolphi` does not
  pull in the `mcp` SDK.
- **Claude Desktop or Cursor does not see the tools** — fully quit and
  relaunch the app. Both clients only read `mcpServers` at startup.
- **Auth / 401 errors** — the Dolphi server is local stdio with no auth.
  401s come from the underlying LLM provider (set keys in `~/.dolphi/.env`
  or pass `mock: true` to skip LLMs entirely).
