"""MCP plumbing: the client our agents use, and the server they talk to.

Named `mcp_layer` rather than `mcp` on purpose — a local package called `mcp`
would shadow the official SDK and produce a very confusing import error.
"""

from .client import MCPRegistry, ServerSpec

__all__ = ["MCPRegistry", "ServerSpec"]
