"""agentic-curator — a teaching framework for orchestrator + subagent systems over MCP.

    from agentic_curator import build_runtime, run_pipeline

Read `docs/01-concepts.md` first, then follow `docs/03-lab-guide.md`.

The two names above are imported lazily so that `import agentic_curator.tools`
stays cheap and does not drag in the MCP SDK.
"""

from typing import Any

__version__ = "0.1.0"
__all__ = ["build_runtime", "run_pipeline", "__version__"]


def __getattr__(name: str) -> Any:  # PEP 562 lazy import
    if name in {"build_runtime", "run_pipeline"}:
        from . import runtime

        return getattr(runtime, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
