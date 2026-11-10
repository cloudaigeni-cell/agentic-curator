"""Pure functions over file content. No agents, no MCP, no LLM — easy to unit test.

Keeping the real work in plain functions is a habit worth copying: when an
agent misbehaves you want to be able to ask "is the *logic* wrong, or is the
*agent* wrong?" and answer it in a REPL.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

DOCUMENT_EXT = {".txt", ".md", ".pdf", ".csv", ".json", ".log", ".rst"}
PHOTO_EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"}

_MONTHS = (
    "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|"
    "june|july|august|september|october|november|december"
)
# A bare year (report_2019) or the start of a date stamp (IMG_20190704).
_YEAR_IN_NAME = re.compile(r"(?<!\d)(19[7-9]\d|20[0-4]\d)(?:(?=[01]\d[0-3]\d(?!\d))|(?!\d))")


def classify(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in PHOTO_EXT:
        return "photo"
    if ext in DOCUMENT_EXT:
        return "document"
    return "other"


def sha256_file(path: Path, *, chunk: int = 1 << 20) -> str:
    """Streaming hash — a 4 GB video must not become a 4 GB string."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def extract_text(path: Path, *, max_chars: int = 20_000) -> str:
    """Best-effort text for documents. Returns '' when there is nothing to read."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _pdf_text(path, max_chars=max_chars)
    if ext in {".txt", ".md", ".csv", ".json", ".log", ".rst"}:
        try:
            return path.read_text(encoding="utf-8", errors="replace")[:max_chars]
        except OSError:
            return ""
    return ""


def _pdf_text(path: Path, *, max_chars: int) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover - dependency is declared, guard anyway
        return ""
    try:
        reader = PdfReader(str(path))
    except Exception:  # noqa: BLE001 - corrupt PDFs are data, not crashes
        return ""
    out: list[str] = []
    total = 0
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001
            continue
        out.append(text)
        total += len(text)
        if total >= max_chars:
            break
    return "\n".join(out)[:max_chars]


def year_hint(path: Path, mtime: float) -> int:
    """Which year does this item belong to?

    Filename first (`report_2019.pdf`, `IMG_20200102_...`), modification time
    as the fallback. Filename wins because a file copied last week still
    belongs to the year it is *about* — exactly the kind of domain rule you
    want in code rather than in a prompt.
    """
    import datetime as _dt

    match = _YEAR_IN_NAME.search(path.name)
    if match:
        return int(match.group(1))
    return _dt.datetime.fromtimestamp(mtime).year


def normalise_subject(text: str, filename: str) -> str:
    """A cheap, deterministic subject key used when no LLM is configured."""
    stem = re.sub(r"[_\-\s]+", " ", Path(filename).stem.lower())
    stem = re.sub(r"\b(19[7-9]\d|20[0-4]\d)\b", "", stem)
    stem = re.sub(r"\(\d+\)", "", stem)
    stem = re.sub(r"\b(copy|final|v\d+|draft|small|" + _MONTHS + r")\b", "", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    if stem:
        return stem
    words = re.findall(r"[a-z]{4,}", text.lower())
    return " ".join(words[:3]) if words else "unsorted"
