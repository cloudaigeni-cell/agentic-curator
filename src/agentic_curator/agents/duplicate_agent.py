"""Subagent #3 — duplicate documents.

Two very different questions, deliberately answered by two different methods:

    IDENTICAL   same sha256         -> certainty 1.00, safe to act on
    NEAR-IDENTICAL  Jaccard >= 0.80 -> a *candidate*, needs review

The agent never deletes. It emits `Proposal` objects carrying the evidence that
justified them (the shared hash, or the pairwise similarity scores). A reviewer
can recompute either number in ten seconds, which is the point: an agentic
system earns trust by being checkable, not by being confident.

Which file survives a group? The oldest `modified` time — the original, not the
copy that a sync client made last Tuesday. That rule is in code, where you can
argue with it, rather than in a prompt, where you cannot.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..core.agent import BaseAgent
from ..core.messages import FileRecord, Proposal, TaskSpec
from ..tools.similarity import group_by_similarity


class DuplicateAgent(BaseAgent):
    handles = ("dup.documents",)
    description = "Finds byte-identical and near-identical documents; proposes which copy to keep."
    name = "duplicate-finder"

    async def run(self, task: TaskSpec) -> dict[str, Any]:
        threshold: float = task.payload.get("threshold", 0.80)
        records: list[FileRecord] = await self.ctx.blackboard.get("records", [])
        texts: dict[str, str] = await self.ctx.blackboard.get("doc_texts", {})
        by_path = {r.path: r for r in records}

        proposals: list[Proposal] = []

        # ---- 1. byte-identical -------------------------------------------
        by_hash: dict[str, list[FileRecord]] = defaultdict(list)
        for record in records:
            if record.sha256 and record.kind != "photo":
                by_hash[record.sha256].append(record)

        exact_groups = []
        for digest, members in by_hash.items():
            if len(members) < 2:
                continue
            members.sort(key=lambda r: (r.modified, r.path))
            keeper, duplicates = members[0], members[1:]
            exact_groups.append(
                {
                    "sha256": digest,
                    "keeping": keeper.path,
                    "removing": [r.path for r in duplicates],
                    "bytes_recovered": sum(r.size for r in duplicates),
                }
            )
            proposals.append(
                Proposal(
                    action="delete",
                    targets=[r.path for r in duplicates],
                    reason=f"byte-identical to {keeper.path}",
                    evidence={
                        "method": "sha256",
                        "sha256": digest,
                        "keeping": keeper.path,
                        "bytes_recovered": sum(r.size for r in duplicates),
                    },
                    confidence=1.0,  # the only place this framework claims certainty
                    proposed_by=self.name,
                    group_id=f"exact:{digest[:12]}",
                )
            )

        # ---- 2. near-identical text --------------------------------------
        candidate_texts = {
            path: text for path, text in texts.items() if path in by_path and len(text) > 40
        }
        near_groups = []
        for cluster in group_by_similarity(candidate_texts, threshold=threshold):
            members = [by_path[p] for p in cluster["members"] if p in by_path]
            if len(members) < 2:
                continue
            # Skip clusters already fully explained by an exact-duplicate group.
            hashes = {m.sha256 for m in members}
            if len(hashes) == 1 and None not in hashes:
                continue
            members.sort(key=lambda r: (-r.size, r.modified))
            keeper = members[0]  # keep the longest: the fullest version
            duplicates = members[1:]
            near_groups.append(
                {
                    "keeping": keeper.path,
                    "candidates": [r.path for r in duplicates],
                    "min_similarity": cluster["min_score"],
                    "pair_scores": cluster["pair_scores"],
                }
            )
            proposals.append(
                Proposal(
                    action="merge",  # NOT delete: a near-duplicate needs a human or the consolidator
                    targets=[r.path for r in members],
                    reason=f"text similarity >= {threshold:.0%} across {len(members)} files",
                    evidence={
                        "method": "jaccard-shingles",
                        "pair_scores": cluster["pair_scores"],
                        "min_score": cluster["min_score"],
                        "keeping": keeper.path,
                    },
                    confidence=round(min(0.89, cluster["min_score"]), 3),
                    proposed_by=self.name,
                    group_id=f"near:{keeper.path}",
                )
            )

        await self.ctx.blackboard.propose(proposals)
        await self.ctx.blackboard.put(
            "duplicate_report",
            {"exact": exact_groups, "near": near_groups},
            by=self.name,
            task_id=task.id,
        )

        recovered = sum(g["bytes_recovered"] for g in exact_groups)
        self.ctx.tracer.agent(
            self.name,
            f"{len(exact_groups)} identical group(s), {len(near_groups)} near-identical",
            recoverable_mb=round(recovered / 1_000_000, 2),
        )
        return {
            "exact_groups": len(exact_groups),
            "near_groups": len(near_groups),
            "bytes_recoverable": recovered,
            "proposals": len(proposals),
        }
