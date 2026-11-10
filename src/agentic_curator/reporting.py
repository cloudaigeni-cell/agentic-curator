"""Turn a run into something a human can act on.

Three artefacts per run, all in `runs/<run-id>/`:

    plan.json     machine-readable: every proposal, its evidence, the token
    report.md     human-readable: what was found, what is proposed, what to check
    trace.jsonl   the full event stream (written live by the tracer)

`plan.json` is the file you review before passing `--execute`. It carries the
approval token, so a reviewer can see exactly what that token covers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import Settings


def write_reports(
    run_dir: Path, settings: Settings, summary: dict[str, Any], board: dict[str, Any]
) -> Path:
    plan = {
        "approval_token": summary.get("approval_token"),
        "library": str(settings.library),
        "dry_run": not settings.execute,
        "proposals": board.get("proposals", []),
        "rejected_by_policy": summary.get("rejected_by_policy", []),
        "policy": settings.policy.describe(),
    }
    (run_dir / "plan.json").write_text(json.dumps(plan, indent=2, default=str), encoding="utf-8")

    report = run_dir / "report.md"
    report.write_text(_markdown(settings, summary, board), encoding="utf-8")
    return report


def _mb(value: Any) -> str:
    try:
        return f"{float(value) / 1_000_000:.2f} MB"
    except (TypeError, ValueError):
        return "0.00 MB"


def _markdown(settings: Settings, summary: dict[str, Any], board: dict[str, Any]) -> str:
    inventory = summary.get("inventory", {})
    proposals = board.get("proposals", [])
    deletes = [p for p in proposals if p["action"] == "delete"]
    merges = [p for p in proposals if p["action"] == "merge"]
    reviews = [p for p in proposals if p["action"] == "review"]

    lines = [
        "# Curation run report",
        "",
        f"- **Library:** `{settings.library}`",
        f"- **Files scanned:** {inventory.get('files', 0)} across "
        f"{len(inventory.get('years', []))} year(s)",
        f"- **Model provider:** {settings.provider}",
        f"- **Mode:** {'EXECUTED' if settings.execute else 'dry run (nothing changed)'}",
        f"- **MCP tool calls:** {summary.get('mcp_calls', 0)}",
        f"- **Approval token:** `{summary.get('approval_token', '')}`",
        "",
        "## Headline",
        "",
        f"{len(deletes)} delete group(s) covering "
        f"{sum(len(p['targets']) for p in deletes)} file(s), "
        f"recovering {_mb(summary.get('bytes_recoverable'))}.",
        "",
    ]

    # --- per year ---------------------------------------------------------
    years = summary.get("year_results", [])
    if years:
        lines += [
            "## Per-year breakdown",
            "",
            "| Year | Files | Size | Photos | Documents | Other |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for entry in sorted(years, key=lambda e: e.get("year", 0)):
            lines.append(
                f"| {entry.get('year')} | {entry.get('files')} | {entry.get('megabytes')} MB "
                f"| {entry.get('photos')} | {entry.get('documents')} | {entry.get('other')} |"
            )
        lines.append("")

    # --- proposals --------------------------------------------------------
    if deletes:
        lines += [
            "## Proposed deletions",
            "",
            "Each row keeps one file and retires the rest. Evidence is the measurement "
            "that justified it — recheck any of these yourself before approving.",
            "",
            "| Keep | Remove | Method | Confidence | Recovers |",
            "| --- | --- | --- | --- | --- |",
        ]
        for proposal in sorted(deletes, key=lambda p: -p["confidence"]):
            evidence = proposal.get("evidence", {})
            targets = proposal["targets"]
            shown = ", ".join(f"`{t}`" for t in targets[:3])
            if len(targets) > 3:
                shown += f" +{len(targets) - 3} more"
            lines.append(
                f"| `{evidence.get('keeping', '—')}` | {shown} | {evidence.get('method', '?')} "
                f"| {proposal['confidence']:.2f} | {_mb(evidence.get('bytes_recovered', 0))} |"
            )
        lines.append("")

    if merges:
        lines += ["## Near-identical documents (needs a human)", ""]
        for proposal in merges:
            lines.append(
                f"- {', '.join(f'`{t}`' for t in proposal['targets'])} — "
                f"min similarity {proposal['evidence'].get('min_score', 0):.2f}"
            )
        lines.append("")

    if reviews:
        lines += ["## Similar photos (same scene, different moment)", ""]
        for proposal in reviews:
            lines.append("- " + ", ".join(f"`{t}`" for t in proposal["targets"]))
        lines.append("")

    consolidation = board.get("state_keys", [])
    if "consolidation_report" in consolidation:
        lines += [
            "## Consolidation",
            "",
            f"{summary.get('consolidation', {}).get('subjects_merged', 0)} merged file(s) "
            f"written to `curated/`, absorbing "
            f"{summary.get('consolidation', {}).get('files_absorbed', 0)} source file(s). "
            "Each merge was read back and verified before its sources were proposed for removal.",
            "",
        ]

    rejected = summary.get("rejected_by_policy", [])
    if rejected:
        lines += ["## Blocked by the safety policy", ""]
        for entry in rejected:
            lines.append(f"- `{entry.get('id')}`: {entry.get('reason')}")
        lines.append("")

    review = summary.get("model_review", {})
    if review:
        lines += [
            "## Second opinion",
            "",
            f"- verdict: **{review.get('verdict', 'n/a')}** (source: {review.get('_source', '?')})",
        ]
        for concern in review.get("concerns", [])[:10]:
            lines.append(f"- concern: {concern}")
        lines.append("")

    execution = summary.get("execution", {})
    lines += [
        "## What happened",
        "",
        f"- files moved to trash: **{execution.get('moved', 0)}**",
        f"- note: {execution.get('note', 'executed')}",
        "",
        "## Next step",
        "",
    ]
    if settings.execute:
        lines += [
            "Files were moved to `.curator_trash/` inside the library, with "
            "`manifest.jsonl` recording every original path. Nothing was permanently deleted.",
        ]
    else:
        lines += [
            "Review `plan.json`, then re-run with `--execute` to apply exactly this plan:",
            "",
            "```bash",
            f"curator run --library {settings.library} --execute",
            "```",
            "",
            "If the library changed since this run, the approval token will no longer match "
            "and the deletion agent will refuse — re-run the plan first.",
        ]
    return "\n".join(lines) + "\n"
