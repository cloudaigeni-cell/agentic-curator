"""The safety gate. Read this file before you point the framework at real data.

An agentic system that can delete files is a system that can delete the wrong
files. The defence here is not "the LLM is careful" — it is four mechanical
rules that hold even if every model in the stack misbehaves:

  1. DRY RUN BY DEFAULT.  Nothing is touched unless you pass --execute.
  2. SEPARATION.          The agent that proposes a delete cannot perform it.
  3. APPROVAL TOKEN.      Execution needs a token derived from the exact plan.
                          Change one path and the old token stops working.
  4. TRASH, NEVER unlink. Files move to .curator_trash/ with a manifest.

Rule 3 is the interesting one for learning: it is how you let an autonomous
system act without letting it widen its own mandate between approval and
execution.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from .messages import Proposal


class PolicyViolation(RuntimeError):
    """Raised when an agent tries to do something the policy forbids."""


@dataclass
class SafetyPolicy:
    dry_run: bool = True
    require_approval: bool = True
    max_deletes_per_run: int = 50
    min_confidence_to_delete: float = 0.90
    # Never proposed, never deleted, whatever any agent says.
    protected_globs: tuple[str, ...] = (
        "*.key",
        "*.pem",
        "**/.git/**",
        "**/originals/**",
        ".curator_trash/**",
    )
    keep_one_per_group: bool = True
    audit: list[dict[str, Any]] = field(default_factory=list)

    # -- checks ------------------------------------------------------------
    def is_protected(self, path: str) -> bool:
        return any(fnmatch.fnmatch(path, pattern) for pattern in self.protected_globs)

    def vet(self, proposals: list[Proposal]) -> tuple[list[Proposal], list[dict[str, Any]]]:
        """Split proposals into (allowed, rejected-with-reason).

        Called before a human ever sees the plan, so the list presented for
        approval is already policy-clean.
        """
        allowed: list[Proposal] = []
        rejected: list[dict[str, Any]] = []
        deletes = 0

        for proposal in proposals:
            if proposal.action != "delete":
                allowed.append(proposal)
                continue

            protected = [t for t in proposal.targets if self.is_protected(t)]
            if protected:
                rejected.append({"id": proposal.id, "reason": "protected path", "paths": protected})
                continue

            if proposal.confidence < self.min_confidence_to_delete:
                rejected.append(
                    {
                        "id": proposal.id,
                        "reason": f"confidence {proposal.confidence:.2f} < "
                        f"{self.min_confidence_to_delete:.2f}",
                        "paths": proposal.targets,
                    }
                )
                continue

            if self.keep_one_per_group and not proposal.evidence.get("keeping"):
                rejected.append(
                    {
                        "id": proposal.id,
                        "reason": "no survivor recorded for this group",
                        "paths": proposal.targets,
                    }
                )
                continue

            if deletes + len(proposal.targets) > self.max_deletes_per_run:
                rejected.append(
                    {
                        "id": proposal.id,
                        "reason": f"would exceed max_deletes_per_run={self.max_deletes_per_run}",
                        "paths": proposal.targets,
                    }
                )
                continue

            deletes += len(proposal.targets)
            allowed.append(proposal)

        self.audit.append({"vetted": len(proposals), "allowed": len(allowed), "rejected": rejected})
        return allowed, rejected

    # -- approval ----------------------------------------------------------
    @staticmethod
    def plan_token(proposals: list[Proposal]) -> str:
        """A fingerprint of exactly what was approved.

        Sorted so ordering cannot change the token; includes action + targets so
        swapping a path invalidates it.
        """
        material = sorted(f"{p.action}:{','.join(sorted(p.targets))}" for p in proposals)
        digest = hashlib.sha256("\n".join(material).encode("utf-8")).hexdigest()
        return digest[:16]

    def authorise(self, proposals: list[Proposal], token: str | None) -> None:
        """Gate called by the DeletionAgent immediately before it acts."""
        if self.dry_run:
            raise PolicyViolation("policy is in dry-run mode; nothing may be modified")
        if not self.require_approval:
            return
        expected = self.plan_token(proposals)
        if token != expected:
            raise PolicyViolation(
                f"approval token mismatch (expected {expected}, got {token!r}). "
                "The plan changed since it was approved — re-review it."
            )

    def describe(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "require_approval": self.require_approval,
            "max_deletes_per_run": self.max_deletes_per_run,
            "min_confidence_to_delete": self.min_confidence_to_delete,
            "protected_globs": list(self.protected_globs),
        }

    def to_json(self) -> str:
        return json.dumps(self.describe(), indent=2)
