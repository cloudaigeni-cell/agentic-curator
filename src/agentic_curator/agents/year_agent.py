"""Subagent #1 — one instance per calendar year.

This is the simplest kind of specialisation: *partition the data, clone the
worker*. Nothing about this agent knows there are other years; it is handed a
slice and reports on that slice only.

Why bother? Three reasons you will feel immediately on a real library:

  * parallelism — twelve years hash at once instead of one after another
  * blast radius — a corrupt file in 2014 fails one task, not the run
  * attribution — the trace shows exactly which year cost the time

The orchestrator creates one task per year and the bus runs them concurrently.
That is the whole "subagent per year" pattern: a factory, a task kind, and a
payload that carries the slice.
"""

from __future__ import annotations

from typing import Any

from ..core.agent import BaseAgent
from ..core.messages import FileRecord, TaskSpec


class YearAgent(BaseAgent):
    handles = ("year.analyse",)
    description = "Fingerprints and summarises every file belonging to one year."

    def __init__(self, ctx: Any, year: int | None = None) -> None:
        super().__init__(ctx)
        self.year = year
        # The name carries the year so the trace reads: "year-2019: start ..."
        self.name = f"year-{year}" if year is not None else "year-agent"

    def prepare(self, task: TaskSpec) -> None:
        self.name = f"year-{task.payload['year']}"

    async def run(self, task: TaskSpec) -> dict[str, Any]:
        year = task.payload["year"]
        items: list[dict[str, Any]] = task.payload["items"]

        records: list[FileRecord] = []
        failures: list[dict[str, str]] = []

        for item in items:
            record = FileRecord(
                path=item["path"],
                size=item["size"],
                modified=item["modified"],
                kind=item["kind"],
                ext=item["ext"],
                year=year,
            )
            # The ONE expensive call this agent makes per file. Everything else
            # is arithmetic on data the inventory already produced.
            try:
                hashed = await self.ctx.call_tool(
                    "hash_item", {"path": record.path}, agent=self.name
                )
                record.sha256 = hashed["sha256"]
            except Exception as exc:  # noqa: BLE001 - one bad file must not fail the year
                failures.append({"path": record.path, "error": str(exc)})
            records.append(record)

        # Publish to shared memory. Other agents will pick these up by year.
        await self.ctx.blackboard.merge_list("records", records, by=self.name)

        total_bytes = sum(r.size for r in records)
        summary = {
            "year": year,
            "files": len(records),
            "bytes": total_bytes,
            "megabytes": round(total_bytes / 1_000_000, 2),
            "photos": sum(1 for r in records if r.kind == "photo"),
            "documents": sum(1 for r in records if r.kind == "document"),
            "other": sum(1 for r in records if r.kind == "other"),
            "hash_failures": failures,
        }
        await self.ctx.blackboard.merge_list("year_summaries", [summary], by=self.name)
        self.ctx.tracer.agent(
            self.name,
            f"{summary['files']} files, {summary['megabytes']} MB",
            photos=summary["photos"],
            docs=summary["documents"],
        )
        return summary
