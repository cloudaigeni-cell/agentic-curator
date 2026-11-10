"""Wiring. This file is the map of the whole system — start reading here.

    build_runtime()   create the tracer, blackboard, policy, LLM, MCP registry,
                      then construct every agent and register it on the bus
    run_pipeline()    open the MCP connection, dispatch one `pipeline.run`
                      task, write the reports, optionally execute deletions

Everything above this file is a component; everything below it is a detail.
If you want to add an agent, you add four lines here and nothing else changes.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .agents import (
    ConsolidatorAgent,
    DeletionAgent,
    DocumentAgent,
    DuplicateAgent,
    OrchestratorAgent,
    PhotoDuplicateAgent,
    YearAgent,
)
from .config import Settings
from .core.agent import AgentContext
from .core.blackboard import Blackboard
from .core.bus import AgentBus
from .core.messages import TaskSpec, new_id
from .core.tracing import Tracer
from .llm import build_llm
from .mcp_layer.client import MCPRegistry, ServerSpec
from .reporting import write_reports


@dataclass
class Runtime:
    settings: Settings
    tracer: Tracer
    blackboard: Blackboard
    bus: AgentBus
    registry: MCPRegistry
    ctx: AgentContext
    orchestrator: OrchestratorAgent
    run_dir: Path


def build_runtime(settings: Settings, *, console: bool = True) -> Runtime:
    """Assemble every component. No I/O happens here except creating the run directory."""
    run_id = f"run-{time.strftime('%Y%m%d-%H%M%S')}-{new_id('')[1:5]}"
    run_dir = settings.out_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    tracer = Tracer(run_id=run_id, path=run_dir / "trace.jsonl", console=console)
    tracer.info(f"library={settings.library}  provider={settings.provider}  run={run_id}")

    blackboard = Blackboard()
    registry = MCPRegistry(tracer)
    llm = build_llm(settings.provider, settings.model)
    tracer.info(f"llm provider: {llm.name} ({llm.model})")

    ctx = AgentContext(
        mcp=registry,
        llm=llm,
        blackboard=blackboard,
        policy=settings.policy,
        tracer=tracer,
    )

    bus = AgentBus(tracer, max_concurrency=settings.concurrency)
    orchestrator = OrchestratorAgent(ctx, bus, settings)

    # --- the roster -------------------------------------------------------
    bus.register(orchestrator)
    bus.register(DuplicateAgent(ctx))
    bus.register(PhotoDuplicateAgent(ctx))
    bus.register(ConsolidatorAgent(ctx))
    bus.register(DeletionAgent(ctx))
    # One *fresh instance per task* so each year gets its own agent object.
    bus.register_factory("year.analyse", lambda: YearAgent(ctx))
    bus.register_factory("doc.extract", lambda: DocumentAgent(ctx))

    return Runtime(
        settings=settings,
        tracer=tracer,
        blackboard=blackboard,
        bus=bus,
        registry=registry,
        ctx=ctx,
        orchestrator=orchestrator,
        run_dir=run_dir,
    )


async def run_pipeline(settings: Settings, *, console: bool = True) -> dict[str, Any]:
    """One full curation run. Returns the summary dict that `curator run` prints."""
    runtime = build_runtime(settings, console=console)
    tracer = runtime.tracer

    library = settings.library.expanduser().resolve()
    if not library.is_dir():
        raise FileNotFoundError(f"library not found: {library}")

    async with runtime.registry as registry:
        # Connect once; every agent shares this session.
        await registry.connect(ServerSpec.library(library))

        result = await runtime.bus.dispatch(TaskSpec(kind="pipeline.run", payload={}))
        summary: dict[str, Any] = dict(result.data)

        # --- execution is a separate, explicitly gated step ---------------
        if settings.execute:
            approved = await runtime.blackboard.get("approved_deletes", [])
            if approved:
                token = settings.policy.plan_token(approved)
                tracer.orchestrator("phase 7 · executing approved deletions", token=token)
                deletion = await runtime.bus.dispatch(
                    TaskSpec(kind="delete.execute", payload={"token": token})
                )
                summary["execution"] = deletion.data if deletion.ok else {"error": deletion.error}
            else:
                summary["execution"] = {"moved": 0, "note": "nothing approved"}
        else:
            summary["execution"] = {
                "moved": 0,
                "note": "dry run — re-run with --execute to apply the plan",
            }

        summary["bus"] = runtime.bus.stats()
        summary["mcp_calls"] = registry.call_count
        summary["trace"] = tracer.summary()

    # Reports are written after the MCP session closes: nothing else to touch.
    board = await runtime.blackboard.snapshot()
    (runtime.run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    (runtime.run_dir / "blackboard.json").write_text(
        json.dumps(board, indent=2, default=str), encoding="utf-8"
    )
    report_path = write_reports(runtime.run_dir, settings, summary, board)

    summary["run_dir"] = str(runtime.run_dir)
    summary["report"] = str(report_path)
    tracer.info(f"reports written to {runtime.run_dir}")
    return summary
