"""The orchestrator — the agent that owns the plan, not the work.

It does four things, in this order, and nothing else:

    SCOPE    one MCP call to inventory the library
    FAN OUT  one task per year, run concurrently          -> YearAgent
    PIPELINE documents -> duplicates -> photos -> merge    -> specialists
    DECIDE   vet every proposal through the policy gate

The ordering is explicit because the stages genuinely depend on each other:
you cannot cluster text you have not extracted, and you cannot merge documents
whose subject you do not know. A "let the agents talk until they converge"
design hides those dependencies and is much harder to debug — which is why
this framework makes the orchestrator a plain async function with phases you
can read top to bottom.

The orchestrator never touches a file and never deletes anything. Its output is
a *plan*.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..core.agent import BaseAgent
from ..core.messages import Proposal, TaskSpec

REVIEW_SYSTEM = (
    "You are reviewing an automated clean-up plan for a personal file library. "
    "Be conservative: irreversible loss is much worse than wasted disk space. "
    "Flag anything that looks like a unique original rather than a copy."
)


class OrchestratorAgent(BaseAgent):
    handles = ("pipeline.run",)
    description = "Plans the run, fans work out to specialists, and assembles the final plan."
    name = "orchestrator"

    def __init__(self, ctx: Any, bus: Any, settings: Any) -> None:
        super().__init__(ctx)
        self.bus = bus
        self.settings = settings

    async def run(self, task: TaskSpec) -> dict[str, Any]:
        tracer = self.ctx.tracer

        # -- PHASE 0: scope -------------------------------------------------
        tracer.orchestrator("phase 0 · inventory")
        inventory = await self.ctx.call_tool("list_items", {}, agent=self.name)
        items: list[dict[str, Any]] = inventory["items"]
        if not items:
            return {"error": "library is empty", "root": inventory.get("root")}

        by_year: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for item in items:
            by_year[item["year"]].append(item)
        tracer.orchestrator(
            f"{len(items)} files across {len(by_year)} year(s)",
            years=",".join(str(y) for y in sorted(by_year)),
        )

        # -- PHASE 1: one subagent per year, in parallel ---------------------
        tracer.orchestrator("phase 1 · per-year agents")
        year_tasks = [
            task.child("year.analyse", {"year": year, "items": entries})
            for year, entries in sorted(by_year.items())
        ]
        year_results = await self.bus.gather(year_tasks, concurrency=self.settings.concurrency)
        failed_years = [r.task_id for r in year_results if not r.ok]

        # -- PHASE 2: text and PDFs, also one task per year ------------------
        tracer.orchestrator("phase 2 · document extraction")
        doc_tasks = []
        for year, entries in sorted(by_year.items()):
            paths = [e["path"] for e in entries if e["kind"] == "document"]
            if paths:
                doc_tasks.append(task.child("doc.extract", {"year": year, "paths": paths}))
        doc_results = await self.bus.gather(doc_tasks, concurrency=self.settings.concurrency)

        # -- PHASE 3 & 4: duplicates. Independent of each other, so run both --
        tracer.orchestrator("phase 3 · duplicate detection (documents + photos)")
        dup_results = await self.bus.gather(
            [
                task.child("dup.documents", {"threshold": self.settings.text_similarity}),
                task.child("dup.photos", {"distance": self.settings.photo_distance}),
            ],
            concurrency=2,
        )

        # -- PHASE 5: consolidation -----------------------------------------
        tracer.orchestrator("phase 5 · consolidation")
        merge_result = await self.bus.dispatch(task.child("consolidate.subjects", {"min_group": 2}))

        # -- PHASE 6: vet everything through the policy gate -----------------
        tracer.orchestrator("phase 6 · policy review")
        proposals = await self.ctx.blackboard.proposals()
        allowed, rejected = self.ctx.policy.vet(proposals)
        approved_deletes = [p for p in allowed if p.action == "delete"]
        await self.ctx.blackboard.put("approved_deletes", approved_deletes, by=self.name)

        for entry in rejected:
            tracer.policy(f"rejected {entry['id']}: {entry['reason']}")

        token = self.ctx.policy.plan_token(approved_deletes)
        freed = sum(
            p.evidence.get("bytes_recovered", 0) for p in approved_deletes
        )
        tracer.orchestrator(
            f"plan: {len(approved_deletes)} delete group(s), "
            f"{sum(len(p.targets) for p in approved_deletes)} file(s), "
            f"{freed / 1_000_000:.2f} MB",
            token=token,
        )

        # -- optional: ask the model to sanity-check the plan ----------------
        review = await self._review(approved_deletes)

        return {
            "inventory": {"files": len(items), "years": sorted(by_year)},
            "year_results": [r.data for r in year_results if r.ok],
            "documents": [r.data for r in doc_results if r.ok],
            "duplicates": dup_results[0].data if dup_results[0].ok else {},
            "photos": dup_results[1].data if dup_results[1].ok else {},
            "consolidation": merge_result.data if merge_result.ok else {},
            "approved_delete_groups": len(approved_deletes),
            "approved_delete_files": sum(len(p.targets) for p in approved_deletes),
            "bytes_recoverable": freed,
            "rejected_by_policy": rejected,
            "approval_token": token,
            "model_review": review,
            "failed_year_tasks": failed_years,
        }

    async def _review(self, proposals: list[Proposal]) -> dict[str, Any]:
        """A second opinion on the plan. Advisory only — it cannot approve anything.

        Note what is sent: paths, methods and scores, never file contents. A
        review step that uploads your whole archive to an API to decide whether
        to delete a thumbnail is a bad trade.
        """
        if not proposals:
            return {"verdict": "nothing to review", "_source": "skipped"}

        lines = [
            f"- {p.group_id}: delete {len(p.targets)} file(s), keep "
            f"{p.evidence.get('keeping')}, method {p.evidence.get('method')}, "
            f"confidence {p.confidence}"
            for p in proposals[:40]
        ]
        verdict = await self.ctx.llm.json(
            "Clean-up plan:\n" + "\n".join(lines) + "\n\n"
            'Return {"verdict": "approve|caution", "concerns": ["..."]}',
            system=REVIEW_SYSTEM,
            fallback={
                "verdict": "approve" if all(p.confidence >= 0.95 for p in proposals) else "caution",
                "concerns": [
                    f"{p.group_id} has confidence {p.confidence}"
                    for p in proposals
                    if p.confidence < 0.95
                ],
            },
            max_tokens=400,
        )
        self.ctx.tracer.orchestrator(
            f"model review: {verdict.get('verdict')}", source=verdict.get("_source")
        )
        return verdict
