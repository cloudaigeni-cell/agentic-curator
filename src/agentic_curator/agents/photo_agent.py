"""Subagent #4 — duplicate photos.

Photos break hashing. Re-save a JPEG, rotate it, let a phone write EXIF, and
the bytes change completely while the picture does not. So this agent asks the
MCP server for a *perceptual* fingerprint (dHash) instead and clusters on
Hamming distance.

Distance is not a detail — it is the whole policy:

    0 bits        the same image, re-encoded          -> confident
    1-4 bits      the same shot                        -> confident
    5-10 bits     the same scene, seconds apart        -> NOT a duplicate
    11+ bits      different pictures

The agent proposes deletion only inside the tight band, and for the wider band
it emits a `review` proposal instead: same scene, different moment, human
decides. Burst shots from a camera are exactly the case that tempts an
over-eager deduplicator into deleting the one photo someone wanted.

Which one survives? Largest pixel count, then largest file: the least
compressed copy of the shot.
"""

from __future__ import annotations

from typing import Any

from ..core.agent import BaseAgent
from ..core.messages import FileRecord, Proposal, TaskSpec
from ..tools.imaging import SIMILAR_BITS, cluster, hamming, similarity


class PhotoDuplicateAgent(BaseAgent):
    handles = ("dup.photos",)
    description = "Fingerprints photos perceptually and groups identical or near-identical shots."
    name = "photo-finder"

    async def run(self, task: TaskSpec) -> dict[str, Any]:
        distance: int = task.payload.get("distance", 4)
        records: list[FileRecord] = await self.ctx.blackboard.get("records", [])
        photos = [r for r in records if r.kind == "photo"]
        by_path = {r.path: r for r in photos}

        fingerprints: dict[str, str] = {}
        pixels: dict[str, int] = {}
        unreadable: list[str] = []

        for record in photos:
            signature = await self.ctx.call_tool(
                "image_signature", {"path": record.path}, agent=self.name
            )
            if not signature.get("readable") or not signature.get("phash"):
                unreadable.append(record.path)
                continue
            record.phash = signature["phash"]
            fingerprints[record.path] = signature["phash"]
            width, height = signature.get("width") or 0, signature.get("height") or 0
            pixels[record.path] = width * height

        proposals: list[Proposal] = []
        duplicate_groups: list[dict[str, Any]] = []
        review_groups: list[dict[str, Any]] = []

        # Tight clusters: the same shot.
        for members in cluster(fingerprints, threshold=distance):
            members.sort(key=lambda p: (-pixels.get(p, 0), -by_path[p].size, p))
            keeper, extras = members[0], members[1:]
            scores = {
                f"{keeper} ~ {other}": round(similarity(fingerprints[keeper], fingerprints[other]), 4)
                for other in extras
            }
            worst = min(
                (hamming(fingerprints[keeper], fingerprints[o]) for o in extras), default=0
            )
            recovered = sum(by_path[p].size for p in extras)
            duplicate_groups.append(
                {
                    "keeping": keeper,
                    "removing": extras,
                    "max_distance_bits": worst,
                    "similarity": scores,
                    "bytes_recovered": recovered,
                }
            )
            proposals.append(
                Proposal(
                    action="delete",
                    targets=extras,
                    reason=f"perceptually identical to {keeper} (<= {distance} bits differ)",
                    evidence={
                        "method": "dhash",
                        "keeping": keeper,
                        "max_distance_bits": worst,
                        "similarity": scores,
                        "bytes_recovered": recovered,
                    },
                    # Confidence falls as the fingerprints drift apart.
                    confidence=round(1.0 - (worst / 64) * 4, 3),
                    proposed_by=self.name,
                    group_id=f"photo:{fingerprints[keeper]}",
                )
            )

        # Wider clusters, minus the tight ones: same scene, NOT the same photo.
        already = {p for group in duplicate_groups for p in [group["keeping"], *group["removing"]]}
        for members in cluster(fingerprints, threshold=SIMILAR_BITS):
            remaining = [p for p in members if p not in already]
            if len(remaining) < 2:
                continue
            review_groups.append(
                {
                    "members": sorted(remaining),
                    "note": "same scene, different moment — a human should choose",
                }
            )
            proposals.append(
                Proposal(
                    action="review",
                    targets=sorted(remaining),
                    reason="visually similar but not the same frame",
                    evidence={"method": "dhash", "threshold_bits": SIMILAR_BITS},
                    confidence=0.5,
                    proposed_by=self.name,
                    group_id=f"photo-review:{remaining[0]}",
                )
            )

        await self.ctx.blackboard.propose(proposals)
        await self.ctx.blackboard.put(
            "photo_report",
            {
                "fingerprinted": len(fingerprints),
                "unreadable": unreadable,
                "duplicates": duplicate_groups,
                "review": review_groups,
            },
            by=self.name,
            task_id=task.id,
        )

        recovered = sum(g["bytes_recovered"] for g in duplicate_groups)
        self.ctx.tracer.agent(
            self.name,
            f"{len(duplicate_groups)} duplicate set(s), {len(review_groups)} to review",
            recoverable_mb=round(recovered / 1_000_000, 2),
        )
        return {
            "photos_fingerprinted": len(fingerprints),
            "unreadable": len(unreadable),
            "duplicate_groups": len(duplicate_groups),
            "review_groups": len(review_groups),
            "bytes_recoverable": recovered,
        }
