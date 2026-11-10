# 2 · MCP primer, using this project's server

The Model Context Protocol is a standard way for a program (the **client**) to discover and call **tools** offered by another program (the **server**). Messages are JSON-RPC 2.0. In this project the transport is stdio: the client starts the server as a child process and they talk over its stdin and stdout.

## The three calls that matter

```
client                                   server (curator-library)
  │── initialize ───────────────────────────▶│   versions and capabilities
  │◀─────────────────────── server info ─────│
  │── tools/list ───────────────────────────▶│   "what can you do?"
  │◀──── 8 tools, each with a JSON schema ───│
  │── tools/call {name, arguments} ─────────▶│   do one thing
  │◀───────────── content / structured ──────│
```

`mcp_layer/client.py` does exactly this in `connect()` and `call()`.

## On the wire

A call to hash one file:

```json
{"jsonrpc": "2.0", "id": 7, "method": "tools/call",
 "params": {"name": "hash_item", "arguments": {"path": "documents/invoice_2019_march.txt"}}}
```

The reply carries the result as structured content:

```json
{"jsonrpc": "2.0", "id": 7,
 "result": {"structuredContent": {"path": "documents/invoice_2019_march.txt",
                                   "sha256": "f70c…743c", "size": 528}}}
```

## Writing a tool is one decorator

`mcp_layer/servers/library_server.py`:

```python
@server.tool(description="SHA-256 of a file's bytes. Proves two files are byte-identical.")
def hash_item(path: str) -> dict[str, Any]:
    target = _safe(path)                 # the sandbox check
    return {"path": _rel(target), "sha256": sha256_file(target), "size": target.stat().st_size}
```

The SDK turns the type hints into the JSON schema that `tools/list` returns.

## The eight tools

| Tool | Effect |
| --- | --- |
| `list_items` | Inventory with size, kind and year |
| `stat_item` | Metadata for one file |
| `read_text` | Text of a document or PDF |
| `hash_item` | SHA-256 |
| `image_signature` | Perceptual fingerprint and dimensions |
| `write_text` | Create a text file (merged documents) |
| `move_to_trash` | Reversible removal with a manifest line |
| `trash_manifest` | What is in the trash and where it came from |

There is no delete tool. An agent cannot call what does not exist.

## Try it without any agent

```bash
curator tools --library demo_library

# or drive the server from the official inspector (needs Node.js)
npx @modelcontextprotocol/inspector \
  python -m agentic_curator.mcp_layer.servers.library_server --root demo_library
```

## Use the same server from Claude Desktop or Claude Code

```json
{
  "mcpServers": {
    "curator-library": {
      "command": "wsl",
      "args": ["bash", "-lc",
               "cd ~/agentic-curator && .venv/bin/python -m agentic_curator.mcp_layer.servers.library_server --root ~/library"]
    }
  }
}
```

## SDK version note

This project targets MCP Python SDK **v2**, where the server class is `MCPServer`. In v1 it was `FastMCP`, and result fields were camelCase (`inputSchema`, `structuredContent`). The client reads both spellings — see `_attr()` in `mcp_layer/client.py`.
