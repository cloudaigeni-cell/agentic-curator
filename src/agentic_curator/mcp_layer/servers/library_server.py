"""A real MCP server. This is the only thing in the project that touches files.

Run it by hand to see the protocol for yourself:

    python -m agentic_curator.mcp_layer.servers.library_server --root ./library

It speaks JSON-RPC 2.0 over stdin/stdout. Any MCP client can drive it — our
agents, Claude Desktop, or `npx @modelcontextprotocol/inspector`.

WHY A SERVER AT ALL?
Agents could just call `pathlib` directly. Putting a protocol boundary here buys
three things that matter once the system grows:

  * one audited surface — every file touch is a tool call that can be logged,
    rate-limited or refused in a single place
  * swappability — point the same agents at a Google Drive MCP server and they
    keep working, because they only ever knew the tool names
  * a real sandbox — the server refuses any path outside its root, so a
    confused agent (or a prompt injection inside a document) cannot reach /etc

NOTE ON SDK VERSIONS: this targets the MCP Python SDK v2, where the ergonomic
server class is `MCPServer` (it was called `FastMCP` in v1).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from ...tools.content import classify, extract_text, sha256_file, year_hint
from ...tools.imaging import dhash, image_size

TRASH_DIRNAME = ".curator_trash"

server = MCPServer(
    "curator-library",
    version="0.1.0",
    instructions=(
        "Read-mostly access to one media/document library. Paths are relative to the "
        "library root; absolute paths and '..' are rejected. Deletion is not offered: "
        "the only destructive tool is move_to_trash, which is reversible."
    ),
)


# --------------------------------------------------------------------------
# Sandbox
# --------------------------------------------------------------------------
def _root() -> Path:
    root = Path(os.environ.get("CURATOR_LIBRARY_ROOT", ".")).expanduser().resolve()
    if not root.is_dir():
        raise RuntimeError(f"library root does not exist: {root}")
    return root


def _safe(relative: str) -> Path:
    """Resolve a library-relative path, refusing anything that escapes the root.

    This single function is the security boundary. Everything else trusts it, so
    it is deliberately strict: no absolute paths, no symlink escapes, no '..'.
    """
    root = _root()
    if relative.startswith(("/", "\\")) or (len(relative) > 1 and relative[1] == ":"):
        raise ValueError(f"absolute paths are not allowed: {relative!r}")
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"path escapes the library root: {relative!r}")
    return candidate


def _rel(path: Path) -> str:
    return path.relative_to(_root()).as_posix()


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------
@server.tool(
    description="List files in the library with size, modification time, kind and year hint."
)
def list_items(subdir: str = "", kind: str = "any", limit: int = 5000) -> dict[str, Any]:
    """kind: 'any' | 'photo' | 'document' | 'other'."""
    base = _safe(subdir) if subdir else _root()
    items: list[dict[str, Any]] = []
    for path in sorted(base.rglob("*")):
        if not path.is_file() or TRASH_DIRNAME in path.parts:
            continue
        item_kind = classify(path)
        if kind != "any" and item_kind != kind:
            continue
        stat = path.stat()
        items.append(
            {
                "path": _rel(path),
                "size": stat.st_size,
                "modified": round(stat.st_mtime, 3),
                "ext": path.suffix.lower(),
                "kind": item_kind,
                "year": year_hint(path, stat.st_mtime),
            }
        )
        if len(items) >= limit:
            break
    return {"root": str(_root()), "count": len(items), "items": items}


@server.tool(description="Size, timestamps and kind for one file.")
def stat_item(path: str) -> dict[str, Any]:
    target = _safe(path)
    stat = target.stat()
    return {
        "path": _rel(target),
        "size": stat.st_size,
        "modified": round(stat.st_mtime, 3),
        "created": round(stat.st_ctime, 3),
        "kind": classify(target),
        "ext": target.suffix.lower(),
    }


@server.tool(description="Extract plain text from a document. PDFs are parsed; images return ''.")
def read_text(path: str, max_chars: int = 20000) -> dict[str, Any]:
    target = _safe(path)
    text = extract_text(target, max_chars=max_chars)
    return {"path": _rel(target), "chars": len(text), "truncated": len(text) >= max_chars, "text": text}


@server.tool(description="SHA-256 of a file's bytes. Proves two files are byte-identical.")
def hash_item(path: str) -> dict[str, Any]:
    target = _safe(path)
    return {"path": _rel(target), "sha256": sha256_file(target), "size": target.stat().st_size}


@server.tool(
    description="Perceptual (dHash) fingerprint of an image, for finding visually similar photos."
)
def image_signature(path: str) -> dict[str, Any]:
    target = _safe(path)
    fingerprint = dhash(target)
    size = image_size(target)
    return {
        "path": _rel(target),
        "phash": fingerprint,
        "width": size[0] if size else None,
        "height": size[1] if size else None,
        "readable": fingerprint is not None,
    }


@server.tool(description="Write a UTF-8 text file inside the library (used for merged documents).")
def write_text(path: str, content: str, overwrite: bool = False) -> dict[str, Any]:
    target = _safe(path)
    if target.exists() and not overwrite:
        raise ValueError(f"refusing to overwrite existing file: {path}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"path": _rel(target), "bytes": target.stat().st_size, "created": True}


@server.tool(
    description=(
        "Move a file into .curator_trash/ and record why. Reversible: the original "
        "relative path is stored in the trash manifest. There is no hard-delete tool."
    )
)
def move_to_trash(path: str, reason: str = "") -> dict[str, Any]:
    target = _safe(path)
    if not target.is_file():
        raise ValueError(f"not a file: {path}")

    trash = _root() / TRASH_DIRNAME
    trash.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    destination = trash / f"{stamp}__{target.name}"
    counter = 1
    while destination.exists():
        destination = trash / f"{stamp}__{counter}__{target.name}"
        counter += 1

    original = _rel(target)
    shutil.move(str(target), str(destination))

    manifest = trash / "manifest.jsonl"
    with manifest.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "at": time.time(),
                    "original_path": original,
                    "trash_path": destination.name,
                    "reason": reason,
                }
            )
            + "\n"
        )
    return {"moved": original, "to": f"{TRASH_DIRNAME}/{destination.name}", "reason": reason}


@server.tool(description="Everything currently in the trash, with original paths, for restoring.")
def trash_manifest() -> dict[str, Any]:
    manifest = _root() / TRASH_DIRNAME / "manifest.jsonl"
    if not manifest.exists():
        return {"entries": [], "count": 0}
    entries = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line]
    return {"entries": entries, "count": len(entries)}


# --------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="MCP server exposing one media library.")
    parser.add_argument("--root", default=os.environ.get("CURATOR_LIBRARY_ROOT", "."))
    args = parser.parse_args()
    os.environ["CURATOR_LIBRARY_ROOT"] = str(Path(args.root).expanduser().resolve())
    # Transport is stdio: the client launches this process and talks over the pipes.
    server.run("stdio")


if __name__ == "__main__":
    main()
