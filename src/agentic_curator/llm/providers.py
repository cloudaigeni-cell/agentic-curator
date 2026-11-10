"""Concrete backends. Each one is ~30 lines; the interesting part is what they share.

    offline    no network, no key, deterministic      <- the default
    anthropic  ANTHROPIC_API_KEY                      paid API
    gemini     GOOGLE_API_KEY, or Google ADC + Vertex  Google credentials
    openai     OPENAI_API_KEY, or any compatible base_url (Ollama, vLLM, Groq)

The SDK import happens inside the constructor, not at module import, so you can
run the whole framework with none of them installed.
"""

from __future__ import annotations

import os
from typing import Any

from .base import LLMProvider, LLMResponse


class OfflineProvider(LLMProvider):
    """No model at all — the honest default.

    It never invents an answer. Every call returns empty text, which makes
    `json()` fall through to the agent's deterministic fallback. That is why
    `curator demo` produces a full, correct report with no API key: the
    measurement code does the work, and the model would only add judgement.
    """

    name = "offline"
    model = "none"

    def __init__(self) -> None:
        self.calls = 0

    async def text(
        self, prompt: str, *, system: str = "", max_tokens: int = 1024, temperature: float = 0.0
    ) -> LLMResponse:
        self.calls += 1
        return LLMResponse(text="", model=self.model, provider=self.name, from_fallback=True)


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, model: str = "claude-sonnet-4-5", api_key: str | None = None) -> None:
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("pip install 'agentic-curator[anthropic]'") from exc
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        self.model = model
        self._client = AsyncAnthropic(api_key=key)

    async def text(
        self, prompt: str, *, system: str = "", max_tokens: int = 1024, temperature: float = 0.0
    ) -> LLMResponse:
        message = await self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system or "You are a careful data-curation assistant.",
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in message.content if block.type == "text")
        return LLMResponse(
            text=text,
            model=self.model,
            provider=self.name,
            usage={
                "input_tokens": message.usage.input_tokens,
                "output_tokens": message.usage.output_tokens,
            },
        )


class GeminiProvider(LLMProvider):
    """Google models via API key, or via Vertex AI using Application Default Credentials.

    ADC path (no API key in your shell):
        gcloud auth application-default login
        export GOOGLE_GENAI_USE_VERTEXAI=true
        export GOOGLE_CLOUD_PROJECT=my-project GOOGLE_CLOUD_LOCATION=us-central1
    """

    name = "gemini"

    def __init__(self, model: str = "gemini-2.0-flash", api_key: str | None = None) -> None:
        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("pip install 'agentic-curator[gemini]'") from exc
        self.model = model
        use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in {"1", "true", "yes"}
        if use_vertex:
            self._client = genai.Client(
                vertexai=True,
                project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
                location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
            )
        else:
            key = api_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
            if not key:
                raise RuntimeError("set GOOGLE_API_KEY, or GOOGLE_GENAI_USE_VERTEXAI=true for ADC")
            self._client = genai.Client(api_key=key)

    async def text(
        self, prompt: str, *, system: str = "", max_tokens: int = 1024, temperature: float = 0.0
    ) -> LLMResponse:
        from google.genai import types

        response = await self._client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system or None,
                max_output_tokens=max_tokens,
                temperature=temperature,
            ),
        )
        usage: dict[str, int] = {}
        meta = getattr(response, "usage_metadata", None)
        if meta is not None:
            usage = {
                "input_tokens": getattr(meta, "prompt_token_count", 0) or 0,
                "output_tokens": getattr(meta, "candidates_token_count", 0) or 0,
            }
        return LLMResponse(
            text=response.text or "", model=self.model, provider=self.name, usage=usage
        )


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI, or anything that speaks its chat API: Ollama, vLLM, Groq, Together.

    For a local model in WSL:
        OPENAI_BASE_URL=http://localhost:11434/v1  OPENAI_API_KEY=ollama
    """

    name = "openai"

    def __init__(
        self, model: str = "gpt-4o-mini", api_key: str | None = None, base_url: str | None = None
    ) -> None:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("pip install 'agentic-curator[openai]'") from exc
        self.model = model
        self._client = AsyncOpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY", "not-needed"),
            base_url=base_url or os.environ.get("OPENAI_BASE_URL") or None,
        )

    async def text(
        self, prompt: str, *, system: str = "", max_tokens: int = 1024, temperature: float = 0.0
    ) -> LLMResponse:
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        completion = await self._client.chat.completions.create(
            model=self.model, messages=messages, max_tokens=max_tokens, temperature=temperature
        )
        usage = {}
        if completion.usage:
            usage = {
                "input_tokens": completion.usage.prompt_tokens,
                "output_tokens": completion.usage.completion_tokens,
            }
        return LLMResponse(
            text=completion.choices[0].message.content or "",
            model=self.model,
            provider=self.name,
            usage=usage,
        )


def build_llm(provider: str, model: str | None = None) -> LLMProvider:
    """Factory used by the runtime. Falls back to offline with a clear message."""
    provider = (provider or "offline").lower()
    try:
        if provider == "anthropic":
            return AnthropicProvider(model or "claude-sonnet-4-5")
        if provider in {"gemini", "google"}:
            return GeminiProvider(model or "gemini-2.0-flash")
        if provider in {"openai", "ollama", "compatible"}:
            return OpenAICompatibleProvider(model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
    except RuntimeError as exc:
        print(f"[llm] {provider} unavailable ({exc}); using offline provider instead")
        return OfflineProvider()
    return OfflineProvider()
