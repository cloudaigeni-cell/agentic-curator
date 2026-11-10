"""One interface, four backends, zero lock-in.

Every agent that wants a model calls `ctx.llm.json(...)` or `ctx.llm.text(...)`.
Which company answers is a config line, not a code change.

The `json()` helper matters more than it looks. Models return prose, fenced
code blocks, or trailing apologies; agents need a dict. `json()` does the
parsing, and — importantly — takes a `fallback`. If the model is unavailable,
unparseable, or simply not configured, the agent still gets a usable answer
from deterministic code instead of crashing the run.

That fallback is the difference between a demo and a system.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str
    usage: dict[str, int] = field(default_factory=dict)
    from_fallback: bool = False


class LLMProvider(ABC):
    """Implement `text()`; `json()` comes free."""

    name: str = "base"
    model: str = ""

    @abstractmethod
    async def text(
        self, prompt: str, *, system: str = "", max_tokens: int = 1024, temperature: float = 0.0
    ) -> LLMResponse:
        ...

    async def json(
        self,
        prompt: str,
        *,
        system: str = "",
        fallback: dict[str, Any] | None = None,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        """Ask for JSON, always return a dict.

        On any failure the fallback is returned with `_source` marked, so a
        trace never hides the fact that the model did not actually answer.
        """
        instruction = (
            f"{system}\n\nReply with JSON only. No prose, no code fence." if system
            else "Reply with JSON only. No prose, no code fence."
        )
        try:
            response = await self.text(prompt, system=instruction, max_tokens=max_tokens)
            parsed = extract_json(response.text)
            if parsed is not None:
                parsed.setdefault("_source", f"{self.name}:{self.model}")
                return parsed
        except Exception as exc:  # noqa: BLE001 - the model must never break the pipeline
            if fallback is None:
                raise
            out = dict(fallback)
            out["_source"] = "fallback"
            out["_error"] = f"{type(exc).__name__}: {exc}"
            return out

        out = dict(fallback or {})
        out["_source"] = "fallback"
        out["_error"] = "model reply was not valid JSON"
        return out

    async def aclose(self) -> None:
        """Override if the backend holds a client that should be closed."""


def extract_json(text: str) -> dict[str, Any] | None:
    """Pull the first JSON object out of a model reply. Tolerates fences and chatter."""
    if not text:
        return None
    candidates: list[str] = []
    fence = _FENCE.search(text)
    if fence:
        candidates.append(fence.group(1))
    candidates.append(text)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            value = json.loads(candidate.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(value, dict):
            return value
        if isinstance(value, list):
            return {"items": value}
    return None
