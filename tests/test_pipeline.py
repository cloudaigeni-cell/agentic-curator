"""End to end: a real MCP server process, every agent, the planted sample library."""

import json
from pathlib import Path

import pytest

from agentic_curator.config import Settings
from agentic_curator.core import SafetyPolicy, Tracer
from agentic_curator.mcp_layer import MCPRegistry, ServerSpec
from agentic_curator.runtime import run_pipeline
from agentic_curator.sample import EXPECTED, build_sample_library


@pytest.fixture()
def library(tmp_path: Path) -> Path:
    root = tmp_path / "library"
    build_sample_library(root)
    return root


def _settings(library: Path, tmp_path: Path, execute: bool = False) -> Settings:
    settings = Settings(library=library, out_dir=tmp_path / "runs", execute=execute, policy=SafetyPolicy())
    settings.policy.dry_run = not execute
    return settings


async def test_mcp_server_roundtrip_and_sandbox(library: Path) -> None:
    async with MCPRegistry(Tracer(run_id="t", console=False)) as registry:
        tools = await registry.connect(ServerSpec.library(library))
        assert {"list_items", "hash_item", "image_signature", "move_to_trash"} <= set(tools)
        assert "delete" not in " ".join(tools)  # no hard-delete tool exists at all

        listing = await registry.call("library", "list_items", {})
        assert listing["count"] == 18

        with pytest.raises(RuntimeError):
            await registry.call("library", "read_text", {"path": "../../etc/passwd"})
        with pytest.raises(RuntimeError):
            await registry.call("library", "read_text", {"path": "/etc/passwd"})


async def test_dry_run_finds_planted_mess_and_changes_nothing(library: Path, tmp_path: Path) -> None:
    before = sorted(p.relative_to(library).as_posix() for p in library.rglob("*") if p.is_file())
    summary = await run_pipeline(_settings(library, tmp_path), console=False)

    assert summary["duplicates"]["exact_groups"] == EXPECTED["exact_document_groups"]
    assert summary["duplicates"]["near_groups"] == EXPECTED["near_document_groups"]
    assert summary["photos"]["duplicate_groups"] == EXPECTED["photo_duplicate_groups"]
    assert summary["photos"]["review_groups"] == EXPECTED["photo_review_groups"]
    assert summary["consolidation"]["subjects_merged"] == EXPECTED["merged_subjects"]
    assert summary["execution"]["moved"] == 0

    after = sorted(
        p.relative_to(library).as_posix()
        for p in library.rglob("*")
        if p.is_file() and not p.relative_to(library).as_posix().startswith("curated/")
    )
    assert after == before  # originals untouched; only curated/ was added

    plan = json.loads((Path(summary["run_dir"]) / "plan.json").read_text())
    retiring = {t for p in plan["proposals"] if p["action"] == "delete" for t in p["targets"]}
    # Unique files and the same-scene photos must never be on the list.
    for keeper in (
        "documents/recipe_bread_2020.md",
        "documents/tax_summary_2021.pdf",
        "documents/service_agreement_2020.pdf",
        "photos/IMG_20210321_park_1.jpg",
        "photos/IMG_20210321_park_2.jpg",
        "photos/IMG_20190704_beach.jpg",
    ):
        assert keeper not in retiring


async def test_execute_moves_to_trash_and_is_reversible(library: Path, tmp_path: Path) -> None:
    summary = await run_pipeline(_settings(library, tmp_path, execute=True), console=False)
    assert summary["execution"]["moved"] == summary["approved_delete_files"] == 8

    trash = library / ".curator_trash"
    manifest = [json.loads(line) for line in (trash / "manifest.jsonl").read_text().splitlines()]
    assert len(manifest) == 8
    assert all((trash / entry["trash_path"]).exists() for entry in manifest)
    assert (library / "documents/invoice_2019_march.txt").exists()  # the survivor
    assert (library / "curated/meeting-notes.md").exists()

    # A second run finds nothing left to do.
    again = await run_pipeline(_settings(library, tmp_path), console=False)
    assert again["approved_delete_files"] == 0
