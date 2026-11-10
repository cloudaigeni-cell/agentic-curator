"""Make the invisible visible.

Multi-agent systems fail in ways that are hard to see: a task routed to nobody,
an agent quietly returning an empty list, an LLM call that cost money and
changed nothing. Every such moment emits a trace event here.

Two outputs:
  * a live console tree, indented by task depth, so you watch the run unfold
  * a JSONL file you can replay, diff between runs, or load into a notebook
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ANSI colours; disabled automatically when output is piped to a file.
_COLOURS = {
    "orchestrator": "\033[95m",
    "agent": "\033[96m",
    "mcp": "\033[93m",
    "llm": "\033[92m",
    "policy": "\033[91m",
    "info": "\033[90m",
}
_RESET = "\033[0m"


@dataclass
class Tracer:
    run_id: str
    path: Path | None = None
    console: bool = True
    events: list[dict[str, Any]] = field(default_factory=list)
    _t0: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        self._use_colour = self.console and sys.stdout.isatty()
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("", encoding="utf-8")

    def emit(self, channel: str, message: str, *, depth: int = 0, **fields: Any) -> None:
        event = {
            "t": round(time.time() - self._t0, 4),
            "run": self.run_id,
            "channel": channel,
            "message": message,
            "depth": depth,
            **fields,
        }
        self.events.append(event)
        if self.path:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event) + "\n")
        if self.console:
            self._print(event)

    def _print(self, event: dict[str, Any]) -> None:
        indent = "  " * event["depth"]
        channel = event["channel"]
        tag = f"[{channel}]".ljust(15)
        if self._use_colour:
            tag = f"{_COLOURS.get(channel, '')}{tag}{_RESET}"
        extras = {
            k: v for k, v in event.items() if k not in {"t", "run", "channel", "message", "depth"}
        }
        suffix = ""
        if extras:
            suffix = "  " + " ".join(f"{k}={_short(v)}" for k, v in extras.items())
        print(f"{event['t']:7.3f}s {tag}{indent}{event['message']}{suffix}", flush=True)

    # Convenience wrappers so call sites read like sentences -----------------
    def orchestrator(self, msg: str, **f: Any) -> None:
        self.emit("orchestrator", msg, depth=0, **f)

    def agent(self, name: str, msg: str, **f: Any) -> None:
        self.emit("agent", f"{name}: {msg}", depth=1, **f)

    def mcp(self, msg: str, **f: Any) -> None:
        self.emit("mcp", msg, depth=2, **f)

    def llm(self, msg: str, **f: Any) -> None:
        self.emit("llm", msg, depth=2, **f)

    def policy(self, msg: str, **f: Any) -> None:
        self.emit("policy", msg, depth=1, **f)

    def info(self, msg: str, **f: Any) -> None:
        self.emit("info", msg, depth=0, **f)

    def summary(self) -> dict[str, Any]:
        by_channel: dict[str, int] = {}
        for e in self.events:
            by_channel[e["channel"]] = by_channel.get(e["channel"], 0) + 1
        return {
            "run_id": self.run_id,
            "events": len(self.events),
            "by_channel": by_channel,
            "wall_seconds": round(time.time() - self._t0, 3),
        }


def _short(value: Any, limit: int = 60) -> str:
    text = str(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."
