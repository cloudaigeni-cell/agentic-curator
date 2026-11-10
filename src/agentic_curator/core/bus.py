"""Routing and concurrency.

The bus is small on purpose. It does three jobs:

    register(agent)      build the kind -> agent routing table
    dispatch(task)       run one task on the right agent
    gather(tasks, n)     run many tasks with at most n in flight

`gather` is where the "one subagent per year" idea becomes real: the
orchestrator creates one task per year and the bus runs several of them at
once, each in its own agent instance, each writing to the same blackboard.

There is no magic scheduler and no agent-to-agent chat. If two agents need to
cooperate, the orchestrator sequences them. That constraint is deliberate:
free-form agent chatter is the single most common way these systems become
impossible to debug.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from .agent import BaseAgent
from .messages import AgentResult, TaskSpec, TaskStatus
from .tracing import Tracer


class AgentBus:
    def __init__(self, tracer: Tracer, *, max_concurrency: int = 4, max_retries: int = 1) -> None:
        self.tracer = tracer
        self.max_concurrency = max_concurrency
        self.max_retries = max_retries
        self._routes: dict[str, BaseAgent] = {}
        self._factories: dict[str, Callable[[], BaseAgent]] = {}
        self.results: list[AgentResult] = []

    # -- registration ------------------------------------------------------
    def register(self, agent: BaseAgent) -> None:
        for kind in agent.handles:
            if kind in self._routes:
                raise ValueError(
                    f"task kind {kind!r} already handled by {self._routes[kind].name}; "
                    "two agents claiming one kind makes routing ambiguous"
                )
            self._routes[kind] = agent
        self.tracer.info(f"registered {agent.name}", handles=",".join(agent.handles))

    def register_factory(self, kind: str, factory: Callable[[], BaseAgent]) -> None:
        """For agents you want a *fresh instance of* per task (e.g. one per year)."""
        self._factories[kind] = factory
        self.tracer.info(f"registered factory for {kind}")

    def routing_table(self) -> dict[str, str]:
        table = {k: a.name for k, a in self._routes.items()}
        table.update({k: f"{k}:per-task instance" for k in self._factories})
        return table

    # -- execution ---------------------------------------------------------
    async def dispatch(self, task: TaskSpec) -> AgentResult:
        agent = self._resolve(task.kind)
        if agent is None:
            self.tracer.info(f"no agent handles {task.kind!r} — dropped", task=task.id)
            result = AgentResult(
                task_id=task.id,
                agent="bus",
                status=TaskStatus.SKIPPED,
                error=f"no agent registered for kind {task.kind!r}",
            )
            self.results.append(result)
            return result

        result = await agent.execute(task)
        while not result.ok and task.attempt < self.max_retries:
            task.attempt += 1
            self.tracer.info(f"retry {task.attempt} for {task.kind}", task=task.id)
            result = await agent.execute(task)

        self.results.append(result)
        return result

    async def gather(self, tasks: list[TaskSpec], *, concurrency: int | None = None) -> list[AgentResult]:
        """Run tasks in parallel, bounded. Order of results matches order of tasks."""
        limit = asyncio.Semaphore(concurrency or self.max_concurrency)

        async def _one(task: TaskSpec) -> AgentResult:
            async with limit:
                return await self.dispatch(task)

        return list(await asyncio.gather(*(_one(t) for t in tasks)))

    def _resolve(self, kind: str) -> BaseAgent | None:
        if kind in self._routes:
            return self._routes[kind]
        if kind in self._factories:
            return self._factories[kind]()
        return None

    # -- reporting ---------------------------------------------------------
    def stats(self) -> dict[str, Any]:
        by_agent: dict[str, dict[str, Any]] = {}
        for result in self.results:
            entry = by_agent.setdefault(result.agent, {"tasks": 0, "failed": 0, "ms": 0.0})
            entry["tasks"] += 1
            entry["ms"] = round(entry["ms"] + result.duration_ms, 1)
            if not result.ok:
                entry["failed"] += 1
        return {
            "total_tasks": len(self.results),
            "failed": sum(1 for r in self.results if not r.ok),
            "by_agent": by_agent,
        }
