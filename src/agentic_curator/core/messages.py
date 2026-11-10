"""The vocabulary every agent speaks.

Three objects carry everything in this framework:

    TaskSpec    "here is a unit of work"     orchestrator -> subagent
    AgentResult "here is what I found"       subagent -> orchestrator
    Proposal    "here is what I think should happen"   any agent -> policy gate

The important rule lives in `Proposal`: an agent that *finds* something to
delete is never the agent that *deletes* it. Finding and acting are separated
so a single confused agent cannot destroy data on its own.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


def new_id(prefix: str) -> str:
    """Short, readable, unique-enough ids — they show up in every trace line."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class TaskSpec:
    """A unit of work handed to exactly one agent.

    `kind` is the routing key: the bus looks up which agent declared that it
    `handles` this kind. Nothing else decides routing — no name matching, no
    LLM guessing. That makes the system predictable and easy to debug.
    """

    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: new_id("task"))
    parent_id: str | None = None
    created_at: float = field(default_factory=time.time)
    attempt: int = 0

    def child(self, kind: str, payload: dict[str, Any]) -> TaskSpec:
        """Spawn a subtask that remembers who asked for it."""
        return TaskSpec(kind=kind, payload=payload, parent_id=self.id)


@dataclass
class AgentResult:
    """What an agent hands back. Always returned — failure is data, not an exception."""

    task_id: str
    agent: str
    status: TaskStatus
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    started_at: float = field(default_factory=time.time)
    finished_at: float = 0.0

    @property
    def duration_ms(self) -> float:
        end = self.finished_at or time.time()
        return round((end - self.started_at) * 1000, 1)

    @property
    def ok(self) -> bool:
        return self.status is TaskStatus.DONE

    @classmethod
    def success(cls, task: TaskSpec, agent: str, started: float, **data: Any) -> AgentResult:
        return cls(
            task_id=task.id,
            agent=agent,
            status=TaskStatus.DONE,
            data=data,
            started_at=started,
            finished_at=time.time(),
        )

    @classmethod
    def failure(cls, task: TaskSpec, agent: str, started: float, error: str) -> AgentResult:
        return cls(
            task_id=task.id,
            agent=agent,
            status=TaskStatus.FAILED,
            error=error,
            started_at=started,
            finished_at=time.time(),
        )


@dataclass
class Proposal:
    """A requested change to the library. Nothing here has happened yet.

    Every proposal must carry `evidence` — the actual numbers that justify it
    (matching hashes, similarity scores). A reviewer should be able to check the
    claim without re-running the agent, and without trusting the LLM.
    """

    action: str  # "delete" | "merge" | "keep"
    targets: list[str]  # library-relative paths
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0  # 1.0 only for byte-identical proof
    proposed_by: str = "unknown"
    group_id: str | None = None
    id: str = field(default_factory=lambda: new_id("prop"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "action": self.action,
            "targets": self.targets,
            "reason": self.reason,
            "evidence": self.evidence,
            "confidence": round(self.confidence, 3),
            "proposed_by": self.proposed_by,
            "group_id": self.group_id,
        }


@dataclass
class FileRecord:
    """One item in the library, as every agent sees it.

    Produced once by the inventory step and then passed around. Agents enrich
    it (text summary, perceptual hash) rather than re-reading the disk.
    """

    path: str
    size: int
    modified: float
    kind: str  # "photo" | "document" | "other"
    ext: str
    sha256: str | None = None
    year: int | None = None
    text_excerpt: str | None = None
    subject: str | None = None
    phash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FileRecord:
        known = {f for f in cls.__dataclass_fields__}  # noqa: F821
        return cls(**{k: v for k, v in d.items() if k in known})
