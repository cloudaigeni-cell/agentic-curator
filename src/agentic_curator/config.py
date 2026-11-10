"""Configuration: environment first, flags second, sensible defaults always.

A `.env` file in the working directory is read if present — no dependency, 20
lines of parsing. Copy `.env.example` to `.env` and fill in whichever provider
you actually have.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .core.policy import SafetyPolicy


def load_dotenv(path: Path | str = ".env") -> dict[str, str]:
    """Minimal KEY=VALUE reader. Existing environment variables always win."""
    file = Path(path)
    loaded: dict[str, str] = {}
    if not file.is_file():
        return loaded
    for line in file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        loaded[key] = value
        os.environ.setdefault(key, value)
    return loaded


@dataclass
class Settings:
    library: Path = Path("./library")
    provider: str = "offline"  # offline | anthropic | gemini | openai
    model: str | None = None
    out_dir: Path = Path("./runs")
    concurrency: int = 4
    photo_distance: int = 4  # dHash bits; <= this means "same shot"
    text_similarity: float = 0.80  # Jaccard; >= this means "same document"
    execute: bool = False  # the master switch for destructive actions
    policy: SafetyPolicy = field(default_factory=SafetyPolicy)

    @classmethod
    def from_env(cls, **overrides: object) -> Settings:
        load_dotenv()
        settings = cls(
            library=Path(os.environ.get("CURATOR_LIBRARY", "./library")),
            provider=os.environ.get("CURATOR_PROVIDER", "offline"),
            model=os.environ.get("CURATOR_MODEL") or None,
            out_dir=Path(os.environ.get("CURATOR_OUT", "./runs")),
            concurrency=int(os.environ.get("CURATOR_CONCURRENCY", "4")),
            photo_distance=int(os.environ.get("CURATOR_PHOTO_DISTANCE", "4")),
            text_similarity=float(os.environ.get("CURATOR_TEXT_SIMILARITY", "0.80")),
        )
        for key, value in overrides.items():
            if value is not None and hasattr(settings, key):
                setattr(settings, key, value)
        # The policy's dry_run is the inverse of --execute, and is set in one place.
        settings.policy.dry_run = not settings.execute
        return settings

    def describe(self) -> dict[str, object]:
        return {
            "library": str(self.library),
            "provider": self.provider,
            "model": self.model or "(default)",
            "concurrency": self.concurrency,
            "photo_distance_bits": self.photo_distance,
            "text_similarity_threshold": self.text_similarity,
            "execute": self.execute,
            "policy": self.policy.describe(),
        }
