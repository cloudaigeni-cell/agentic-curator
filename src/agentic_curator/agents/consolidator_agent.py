"""Subagent #5 — combine documents about one subject into a single curated file.

This is the only agent that *creates* data, and it is the one most likely to
lose information if written carelessly. So it follows a rule worth stealing:

    write the new thing, read it back, verify it, and only then propose
    retiring the old things

Concretely: it writes `curated/<subject>.md` through MCP, re-reads it through
MCP, and checks that a fingerprint of every source still appears in the merged
file. If a single source fails that check, no deletion is proposed for the
whole group. A merge that silently dropped a file would otherwise look exactly
like a successful one.

The merged file keeps a provenance header per section — where the text came
from, its size, its date — so the merge is reversible by hand even after the
originals are gone.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from ..core.agent import BaseAgent
from ..core.messages import FileRecord, Proposal, TaskSpec

CURATED_DIR = "curated"
MERGEABLE_EXT = {".txt", ".md", ".rst", ".log"}
VERIFY_CHARS = 120  # how much of each source must survive into the merged file


class ConsolidatorAgent(BaseAgent):
    handles = ("consolidate.subjects",)
    description = "Merges same-subject documents into one curated file and marks sources for retirement."
    name = "consolidator"

    async def run(self, task: TaskSpec) -> dict[str, Any]:
        min_group: int = task.payload.get("min_group", 2)
        records: list[FileRecord] = await self.ctx.blackboard.get("records", [])
        texts: dict[str, str] = await self.ctx.blackboard.get("doc_texts", {})
        subjects: dict[str, str] = await self.ctx.blackboard.get("doc_subjects", {})
        summaries: dict[str, str] = await self.ctx.blackboard.get("doc_summaries", {})
        by_path = {r.path: r for r in records}

        # Files another agent already proved to be byte-identical copies are on
        # their way out; merging them again would only double-count.
        already_retiring = {
            target
            for proposal in await self.ctx.blackboard.proposals("delete")
            for target in proposal.targets
        }

        # Group by subject key produced by the document agent. Only plain-text
        # formats qualify: replacing a PDF with its extracted text would throw
        # away layout, signatures and images, so PDFs are never merged away.
        groups: dict[str, list[str]] = defaultdict(list)
        for path, subject in subjects.items():
            if path not in texts or path not in by_path or path in already_retiring:
                continue
            if by_path[path].ext not in MERGEABLE_EXT or path.startswith(CURATED_DIR + "/"):
                continue
            groups[subject].append(path)

        merged: list[dict[str, Any]] = []
        proposals: list[Proposal] = []
        skipped: list[dict[str, Any]] = []

        for subject, paths in sorted(groups.items()):
            if len(paths) < min_group:
                continue
            paths.sort(key=lambda p: by_path[p].modified)
            slug = _slug(subject)
            target = f"{CURATED_DIR}/{slug}.md"

            document = _render(subject, paths, by_path, texts, summaries)
            try:
                written = await self.ctx.call_tool(
                    "write_text",
                    {"path": target, "content": document, "overwrite": True},
                    agent=self.name,
                )
            except Exception as exc:  # noqa: BLE001
                skipped.append({"subject": subject, "reason": f"write failed: {exc}"})
                continue

            # --- verification: read it back through the same interface ----
            readback = await self.ctx.call_tool(
                "read_text", {"path": target, "max_chars": 200_000}, agent=self.name
            )
            body = readback.get("text", "")
            missing = [p for p in paths if texts[p].strip()[:VERIFY_CHARS] not in body]

            merged.append(
                {
                    "subject": subject,
                    "merged_into": target,
                    "sources": paths,
                    "bytes_written": written.get("bytes", 0),
                    "verified": not missing,
                    "missing_sources": missing,
                }
            )

            if missing:
                skipped.append(
                    {
                        "subject": subject,
                        "reason": f"{len(missing)} source(s) not found in merged file",
                        "paths": missing,
                    }
                )
                self.ctx.tracer.agent(
                    self.name, f"merge NOT trusted for '{subject}' — no deletion proposed"
                )
                continue

            proposals.append(
                Proposal(
                    action="delete",
                    targets=paths,
                    reason=f"content preserved in {target}",
                    evidence={
                        "method": "verified-merge",
                        "keeping": target,
                        "sources_verified": len(paths),
                        "verify_chars": VERIFY_CHARS,
                        "bytes_recovered": sum(by_path[p].size for p in paths),
                    },
                    confidence=0.95,
                    proposed_by=self.name,
                    group_id=f"merge:{slug}",
                )
            )

        await self.ctx.blackboard.propose(proposals)
        await self.ctx.blackboard.put(
            "consolidation_report",
            {"merged": merged, "skipped": skipped},
            by=self.name,
            task_id=task.id,
        )
        self.ctx.tracer.agent(
            self.name, f"{len(merged)} subject file(s) written, {len(skipped)} not trusted"
        )
        return {
            "subjects_merged": len(merged),
            "files_absorbed": sum(len(m["sources"]) for m in merged),
            "skipped": len(skipped),
        }


def _slug(subject: str) -> str:
    keep = [c if c.isalnum() else "-" for c in subject.lower()]
    slug = "".join(keep).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug[:60] or "unsorted"


def _render(
    subject: str,
    paths: list[str],
    records: dict[str, FileRecord],
    texts: dict[str, str],
    summaries: dict[str, str],
) -> str:
    stamp = time.strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# {subject.title()}",
        "",
        f"Merged by agentic-curator on {stamp} from {len(paths)} source file(s).",
        "Each section below keeps its original path, size and date so this merge can be undone.",
        "",
        "## Sources",
        "",
    ]
    for path in paths:
        record = records[path]
        lines.append(
            f"- `{path}` — {record.size:,} bytes, "
            f"{time.strftime('%Y-%m-%d', time.localtime(record.modified))}"
        )
    lines.append("")
    for path in paths:
        record = records[path]
        lines += [
            "---",
            "",
            f"## {path}",
            "",
            f"*Original size {record.size:,} bytes · modified "
            f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(record.modified))}*",
            "",
        ]
        if summaries.get(path):
            lines += [f"> {summaries[path]}", ""]
        lines += [texts[path].strip(), ""]
    return "\n".join(lines)
