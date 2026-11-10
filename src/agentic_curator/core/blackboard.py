"""Shared memory for the agent team.

Agents never call each other directly. They read and write a blackboard, which
means you can add a seventh agent tomorrow without editing the other six.

Two halves:

    state   current best answer for a key  ("inventory", "duplicate_groups")
    facts   append-only log of who wrote what, and when

The fact log is the part you will actually stare at while learning: it is the
provenance trail that explains how a deletion proposal came to exist.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .messages import Proposal


@dataclass
class Fact:
    key: str
    value: Any
    produced_by: str
    task_id: str | None = None
    at: float = field(default_factory=time.time)


class Blackboard:
    """Async-safe shared store. One instance per run."""

    def __init__(self) -> None:
        self._state: dict[str, Any] = {}
        self._facts: list[Fact] = []
        self._proposals: list[Proposal] = []
        self._lock = asyncio.Lock()

    async def put(self, key: str, value: Any, *, by: str, task_id: str | None = None) -> None:
        async with self._lock:
            self._state[key] = value
            self._facts.append(Fact(key=key, value=_summarise(value), produced_by=by, task_id=task_id))

    async def get(self, key: str, default: Any = None) -> Any:
        async with self._lock:
            return self._state.get(key, default)

    async def merge_list(self, key: str, items: list[Any], *, by: str) -> None:
        """Append to a list key — used when many per-year agents report in parallel."""
        async with self._lock:
            bucket = self._state.setdefault(key, [])
            bucket.extend(items)
            self._facts.append(
                Fact(key=key, value=f"+{len(items)} items (total {len(bucket)})", produced_by=by)
            )

    async def merge_dict(self, key: str, values: dict[str, Any], *, by: str) -> None:
        """Merge into a dict key — used when per-year document agents report in parallel."""
        if not values:
            return
        async with self._lock:
            bucket = self._state.setdefault(key, {})
            bucket.update(values)
            self._facts.append(
                Fact(key=key, value=f"+{len(values)} keys (total {len(bucket)})", produced_by=by)
            )

    async def propose(self, proposals: list[Proposal]) -> None:
        async with self._lock:
            self._proposals.extend(proposals)

    async def proposals(self, action: str | None = None) -> list[Proposal]:
        async with self._lock:
            if action is None:
                return list(self._proposals)
            return [p for p in self._proposals if p.action == action]

    async def snapshot(self) -> dict[str, Any]:
        async with self._lock:
            return {
                "state_keys": sorted(self._state),
                "facts": [
                    {"key": f.key, "by": f.produced_by, "value": f.value, "at": round(f.at, 3)}
                    for f in self._facts
                ],
                "proposals": [p.to_dict() for p in self._proposals],
            }

    async def dump(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(await self.snapshot(), indent=2), encoding="utf-8")
        return path


def _summarise(value: Any) -> Any:
    """Keep the fact log readable: store a shape, not a megabyte of payload."""
    if isinstance(value, list):
        return f"list[{len(value)}]"
    if isinstance(value, dict):
        return f"dict{sorted(value)[:6]}"
    if isinstance(value, str) and len(value) > 120:
        return value[:117] + "..."
    return value
