"""The MCP client side: how an agent reaches a tool it does not own.

The flow, once per server, at startup:

    launch the server process (stdio)
      -> open a ClientSession over its pipes
      -> session.initialize()          capability handshake
      -> session.list_tools()          discover what exists
    ... then, many times ...
      -> session.call_tool(name, args) a JSON-RPC request/response

`MCPRegistry` holds several such connections under short names ("library",
"drive") and keeps them alive for the length of a run, because spawning a
process per tool call would dominate the runtime.

Learning note: nothing below is agent-specific. This is just an MCP client —
the same code would let a plain script use the same tools.
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ..core.tracing import Tracer


@dataclass
class ServerSpec:
    """How to start one MCP server. Mirrors a Claude Desktop config entry."""

    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)

    @classmethod
    def library(cls, root: Path, *, name: str = "library") -> ServerSpec:
        """The bundled server, pointed at a library directory."""
        # client.py -> mcp_layer -> agentic_curator -> src
        src = str(Path(__file__).resolve().parents[2])
        env = {
            "CURATOR_LIBRARY_ROOT": str(Path(root).expanduser().resolve()),
            # The child process needs to import this package.
            "PYTHONPATH": src + os.pathsep + os.environ.get("PYTHONPATH", ""),
            "PATH": os.environ.get("PATH", ""),
        }
        return cls(
            name=name,
            command=sys.executable,
            args=["-m", "agentic_curator.mcp_layer.servers.library_server", "--root", str(root)],
            env=env,
        )


class MCPRegistry:
    """Named, long-lived MCP connections.

    Use as an async context manager:

        async with MCPRegistry(tracer) as reg:
            await reg.connect(ServerSpec.library(Path("library")))
            await reg.call("library", "list_items", {})
    """

    def __init__(self, tracer: Tracer) -> None:
        self.tracer = tracer
        self._stack = AsyncExitStack()
        self._sessions: dict[str, ClientSession] = {}
        self._tools: dict[str, list[dict[str, Any]]] = {}
        self.call_count = 0

    async def __aenter__(self) -> MCPRegistry:
        await self._stack.__aenter__()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self._stack.aclose()
        self._sessions.clear()

    async def connect(self, spec: ServerSpec) -> list[str]:
        """Start a server, handshake, and discover its tools. Returns tool names."""
        params = StdioServerParameters(command=spec.command, args=spec.args, env=spec.env)
        read, write = await self._stack.enter_async_context(stdio_client(params))
        session = await self._stack.enter_async_context(ClientSession(read, write))

        init = await session.initialize()
        listed = await session.list_tools()

        self._sessions[spec.name] = session
        self._tools[spec.name] = [
            {
                "name": tool.name,
                "description": (tool.description or "").strip(),
                "schema": _attr(tool, "input_schema", "inputSchema") or {},
            }
            for tool in listed.tools
        ]
        names = [t["name"] for t in self._tools[spec.name]]
        info = _attr(init, "server_info", "serverInfo")
        self.tracer.mcp(
            f"connected '{spec.name}' ({getattr(info, 'name', '?')})", tools=len(names)
        )
        return names

    async def call(self, server: str, tool: str, arguments: dict[str, Any]) -> Any:
        """Call a tool and return plain Python data.

        MCP replies are a list of content blocks. Servers built with typed
        Python functions also return `structuredContent`, which is the
        convenient path; we fall back to parsing the text block so this client
        works against servers written in any language.
        """
        session = self._sessions.get(server)
        if session is None:
            raise KeyError(f"no MCP server registered as {server!r}")

        self.call_count += 1
        result = await session.call_tool(tool, arguments)

        if _attr(result, "is_error", "isError"):
            detail = _first_text(result) or "unknown error"
            raise RuntimeError(f"MCP tool {server}.{tool} failed: {detail}")

        structured = _attr(result, "structured_content", "structuredContent")
        if structured:
            # Typed servers wrap a bare return value under "result".
            if set(structured) == {"result"}:
                return structured["result"]
            return structured

        text = _first_text(result)
        if text is None:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    def tools(self, server: str | None = None) -> dict[str, list[dict[str, Any]]]:
        if server:
            return {server: self._tools.get(server, [])}
        return dict(self._tools)

    def describe_for_prompt(self, server: str) -> str:
        """Compact tool catalogue to paste into an LLM prompt."""
        lines = []
        for tool in self._tools.get(server, []):
            params = ", ".join((tool["schema"] or {}).get("properties", {}))
            lines.append(f"- {tool['name']}({params}): {tool['description']}")
        return "\n".join(lines)


def _attr(obj: Any, *names: str) -> Any:
    """Read the first attribute that exists.

    MCP SDK v1 used camelCase (`inputSchema`), v2 uses snake_case
    (`input_schema`). Rather than pinning one SDK version, we accept both — a
    small habit that saves a lot of breakage when a protocol SDK moves fast.
    """
    for name in names:
        value = getattr(obj, name, None)
        if value is not None:
            return value
    return None


def _first_text(result: Any) -> str | None:
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text is not None:
            return text
    return None
