"""What an agent *is* in this framework.

An agent is four things and nothing more:

    name       who it is in the trace
    handles    the task kinds it accepts  (routing is explicit, not inferred)
    run()      the work, async, returning an AgentResult
    ctx        shared services: MCP tools, an LLM, the blackboard, the policy

Notice what is *not* here: no inheritance tree of "ReActAgent" or
"ToolCallingAgent", no hidden prompt. If an agent wants the model it asks
`ctx.llm`; if it wants the disk it asks `ctx.mcp`. Everything an agent can do
is visible at its call sites, which is what makes this readable as a teaching
codebase.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .blackboard import Blackboard
from .messages import AgentResult, TaskSpec
from .policy import SafetyPolicy
from .tracing import Tracer

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters for type checkers
    from ..llm.base import LLMProvider
    from ..mcp_layer.client import MCPRegistry


@dataclass
class AgentContext:
    """Everything an agent is allowed to reach. Passed in, never imported."""

    mcp: "MCPRegistry"
    llm: "LLMProvider"
    blackboard: Blackboard
    policy: SafetyPolicy
    tracer: Tracer
    library_server: str = "library"

    async def call_tool(self, tool: str, arguments: dict[str, Any], *, agent: str) -> Any:
        """Shortcut for the common case: call a tool on the library MCP server."""
        self.tracer.mcp(f"{agent} -> {self.library_server}.{tool}", args=_brief(arguments))
        return await self.mcp.call(self.library_server, tool, arguments)


class BaseAgent(ABC):
    """Subclass this, declare `handles`, implement `run`."""

    name: str = "unnamed"
    handles: tuple[str, ...] = ()
    description: str = ""

    def __init__(self, ctx: AgentContext) -> None:
        self.ctx = ctx

    @abstractmethod
    async def run(self, task: TaskSpec) -> dict[str, Any]:
        """Do the work and return a plain dict. Raise on failure — the bus catches it."""

    async def execute(self, task: TaskSpec) -> AgentResult:
        """Wrapper the bus actually calls: times the work and converts errors to results."""
        started = time.time()
        self.prepare(task)
        self.ctx.tracer.agent(self.name, f"start {task.kind}", task=task.id)
        try:
            data = await self.run(task)
            result = AgentResult.success(task, self.name, started, **(data or {}))
            self.ctx.tracer.agent(
                self.name, f"done {task.kind}", task=task.id, ms=result.duration_ms
            )
            return result
        except Exception as exc:  # noqa: BLE001 - an agent failing must not kill the run
            self.ctx.tracer.agent(self.name, f"FAILED {task.kind}: {exc}", task=task.id)
            return AgentResult.failure(task, self.name, started, f"{type(exc).__name__}: {exc}")

    def prepare(self, task: TaskSpec) -> None:
        """Hook run before the work starts — per-task agents use it to name themselves."""

    def card(self) -> dict[str, Any]:
        """Self-description, printed by `curator agents` and used in orchestrator prompts."""
        return {"name": self.name, "handles": list(self.handles), "description": self.description}


def _brief(arguments: dict[str, Any]) -> str:
    out = []
    for key, value in arguments.items():
        text = str(value)
        out.append(f"{key}={text if len(text) <= 40 else text[:37] + '...'}")
    return " ".join(out)
