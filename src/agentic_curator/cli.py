"""Command line entry point.

    curator demo                     build a messy sample library and run on it
    curator run --library PATH       plan only (dry run)
    curator run --library PATH --execute   apply the plan (moves to trash)
    curator agents                   print the roster and routing table
    curator tools --library PATH     list the MCP tools the server exposes
    curator doctor                   check Python, MCP SDK and provider keys
    curator restore --library PATH   put everything in the trash back
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

from . import __version__
from .config import Settings, load_dotenv


def _settings(args: argparse.Namespace) -> Settings:
    return Settings.from_env(
        library=Path(args.library) if getattr(args, "library", None) else None,
        provider=getattr(args, "provider", None),
        model=getattr(args, "model", None),
        out_dir=Path(args.out) if getattr(args, "out", None) else None,
        concurrency=getattr(args, "concurrency", None),
        execute=bool(getattr(args, "execute", False)),
    )


def _print_summary(summary: dict) -> None:
    execution = summary.get("execution", {})
    print("\n" + "=" * 64)
    print(f" files scanned        {summary.get('inventory', {}).get('files', 0)}")
    print(f" years                {summary.get('inventory', {}).get('years', [])}")
    print(f" delete groups        {summary.get('approved_delete_groups', 0)}")
    print(f" files to retire      {summary.get('approved_delete_files', 0)}")
    print(f" space recoverable    {summary.get('bytes_recoverable', 0) / 1_000_000:.2f} MB")
    print(f" MCP tool calls       {summary.get('mcp_calls', 0)}")
    print(f" agent tasks          {summary.get('bus', {}).get('total_tasks', 0)}")
    print(f" moved to trash       {execution.get('moved', 0)}  ({execution.get('note', 'executed')})")
    print(f" approval token       {summary.get('approval_token')}")
    print(f" report               {summary.get('report')}")
    print("=" * 64)


def cmd_run(args: argparse.Namespace) -> int:
    from .runtime import run_pipeline

    settings = _settings(args)
    summary = asyncio.run(run_pipeline(settings, console=not args.quiet))
    _print_summary(summary)
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    from .runtime import run_pipeline
    from .sample import build_sample_library

    target = Path(args.library or "./demo_library")
    if target.exists() and args.fresh:
        shutil.rmtree(target)
    if not target.exists():
        stats = build_sample_library(target)
        print(f"built sample library at {target}: {stats}")
    args.library = str(target)
    settings = _settings(args)
    summary = asyncio.run(run_pipeline(settings, console=not args.quiet))
    _print_summary(summary)
    if not settings.execute:
        print("\nNothing was changed. Try:  curator demo --execute")
    return 0


def cmd_agents(args: argparse.Namespace) -> int:
    from .runtime import build_runtime

    runtime = build_runtime(_settings(args), console=False)
    print("ROUTING TABLE  (task kind -> agent)")
    for kind, agent in sorted(runtime.bus.routing_table().items()):
        print(f"  {kind:<24} {agent}")
    print("\nPOLICY")
    print(runtime.settings.policy.to_json())
    return 0


def cmd_tools(args: argparse.Namespace) -> int:
    from .core.tracing import Tracer
    from .mcp_layer.client import MCPRegistry, ServerSpec

    async def _list() -> None:
        async with MCPRegistry(Tracer(run_id="tools", console=False)) as registry:
            await registry.connect(ServerSpec.library(Path(args.library)))
            for tool in registry.tools("library")["library"]:
                params = ", ".join((tool["schema"] or {}).get("properties", {}))
                print(f"  {tool['name']}({params})\n      {tool['description']}")

    asyncio.run(_list())
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    load_dotenv()
    ok = True
    print(f"agentic-curator {__version__}")
    print(f"python          {sys.version.split()[0]}  {'OK' if sys.version_info >= (3, 11) else 'need >= 3.11'}")
    for module, label in [("mcp", "MCP SDK"), ("PIL", "Pillow"), ("pypdf", "pypdf")]:
        try:
            __import__(module)
            print(f"{label:<15} OK")
        except ImportError:
            print(f"{label:<15} MISSING  (pip install -e .)")
            ok = False
    print(f"WSL             {'yes' if 'microsoft' in os.uname().release.lower() else 'no (fine on any Linux/macOS)'}")
    print("providers:")
    for name, variable in [
        ("anthropic", "ANTHROPIC_API_KEY"),
        ("gemini", "GOOGLE_API_KEY"),
        ("gemini/vertex", "GOOGLE_GENAI_USE_VERTEXAI"),
        ("openai", "OPENAI_API_KEY"),
    ]:
        print(f"  {name:<14} {'configured' if os.environ.get(variable) else 'not set'}  ({variable})")
    print("  offline        always available")
    return 0 if ok else 1


def cmd_restore(args: argparse.Namespace) -> int:
    library = Path(args.library).expanduser().resolve()
    manifest = library / ".curator_trash" / "manifest.jsonl"
    if not manifest.exists():
        print("trash is empty")
        return 0
    restored = 0
    for line in manifest.read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        source = library / ".curator_trash" / entry["trash_path"]
        target = library / entry["original_path"]
        if source.exists() and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            restored += 1
    manifest.unlink()
    print(f"restored {restored} file(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="curator", description=__doc__.splitlines()[0])
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser, library_required: bool = False) -> None:
        p.add_argument("--library", required=library_required, help="path to the library folder")
        p.add_argument("--provider", choices=["offline", "anthropic", "gemini", "openai"])
        p.add_argument("--model")
        p.add_argument("--out", help="where run folders are written (default ./runs)")
        p.add_argument("--concurrency", type=int)
        p.add_argument("--execute", action="store_true", help="apply the plan (moves to trash)")
        p.add_argument("--quiet", action="store_true", help="hide the live trace")

    p = sub.add_parser("run", help="plan (and optionally apply) a curation run")
    common(p, library_required=True)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("demo", help="generate a sample library and run on it")
    common(p)
    p.add_argument("--fresh", action="store_true", help="rebuild the sample library first")
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("agents", help="show the roster, routing table and policy")
    common(p)
    p.set_defaults(func=cmd_agents)

    p = sub.add_parser("tools", help="list the tools exposed by the MCP server")
    p.add_argument("--library", required=True)
    p.set_defaults(func=cmd_tools)

    p = sub.add_parser("doctor", help="check the environment")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("restore", help="move everything in the trash back")
    p.add_argument("--library", required=True)
    p.set_defaults(func=cmd_restore)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
