"""Subagent #6 — the only agent allowed to remove anything.

Read this one slowly; it is the part that can hurt you.

Four things must all be true before a single file moves:

    1. the policy is not in dry-run              (you passed --execute)
    2. the proposal came from a different agent  (separation of duties)
    3. the approval token matches the plan       (nothing changed since review)
    4. the path is not protected                 (re-checked here, not trusted)

Check 3 is the interesting one. The token is a hash of the exact plan that was
shown to a human. If any agent adds a target between approval and execution,
the hash changes and this agent refuses the whole batch. An autonomous system
cannot quietly widen its own mandate.

And even then it does not delete: it calls `move_to_trash`, which relocates the
file and writes a manifest line. The MCP server offers no hard-delete tool at
all, so this agent could not permanently destroy data even if it tried.
"""

from __future__ import annotations

from typing import Any

from ..core.agent import BaseAgent
from ..core.messages import Proposal, TaskSpec
from ..core.policy import PolicyViolation


class DeletionAgent(BaseAgent):
    handles = ("delete.execute",)
    description = "Moves approved duplicates to trash after verifying policy and approval token."
    name = "deletion-agent"

    async def run(self, task: TaskSpec) -> dict[str, Any]:
        token: str | None = task.payload.get("token")
        proposals: list[Proposal] = await self.ctx.blackboard.get("approved_deletes", [])

        if not proposals:
            self.ctx.tracer.policy("nothing approved for deletion")
            return {"moved": 0, "skipped": 0, "note": "no approved proposals"}

        # Gate 1-3. Raises PolicyViolation, which the bus turns into a failed
        # result — the run continues, nothing is touched.
        try:
            self.ctx.policy.authorise(proposals, token)
        except PolicyViolation as exc:
            self.ctx.tracer.policy(f"REFUSED: {exc}")
            raise

        self.ctx.tracer.policy(
            f"authorised {sum(len(p.targets) for p in proposals)} file(s) in "
            f"{len(proposals)} group(s)"
        )

        moved: list[dict[str, Any]] = []
        refused: list[dict[str, Any]] = []

        for proposal in proposals:
            if proposal.action != "delete":
                refused.append({"id": proposal.id, "reason": f"action is {proposal.action}"})
                continue
            keeping = proposal.evidence.get("keeping")

            for target in proposal.targets:
                # Gate 4: never trust the proposal's own view of what is safe.
                if self.ctx.policy.is_protected(target):
                    refused.append({"path": target, "reason": "protected path"})
                    continue
                if keeping and target == keeping:
                    refused.append({"path": target, "reason": "this is the file we are keeping"})
                    continue
                try:
                    result = await self.ctx.call_tool(
                        "move_to_trash",
                        {"path": target, "reason": f"{proposal.reason} [{proposal.id}]"},
                        agent=self.name,
                    )
                    moved.append(
                        {"path": target, "trash": result["to"], "group": proposal.group_id}
                    )
                except Exception as exc:  # noqa: BLE001
                    refused.append({"path": target, "reason": str(exc)})

        await self.ctx.blackboard.put(
            "deletion_report", {"moved": moved, "refused": refused}, by=self.name, task_id=task.id
        )
        self.ctx.tracer.policy(f"moved {len(moved)} file(s) to trash, refused {len(refused)}")
        return {
            "moved": len(moved),
            "refused": len(refused),
            "details": moved[:20],
            "refusals": refused[:20],
        }
