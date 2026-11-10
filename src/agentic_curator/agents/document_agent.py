"""Subagent #2 — text and PDF.

Turns bytes into something the rest of the team can reason about: an excerpt
and a *subject key*. The subject key is what later lets the consolidator say
"these four files are all about the Q3 migration".

This is the first agent that may call a model, and it shows the house rule:

    code measures, the model judges, code checks the judgement

The deterministic `normalise_subject()` always runs and always produces an
answer. The model is asked to improve it. If the model is offline, wrong, or
returns nonsense, the heuristic result stands and the run continues. You can
see which happened in the trace — look for `source=offline:none` versus
`source=anthropic:claude-...`.
"""

from __future__ import annotations

from typing import Any

from ..core.agent import BaseAgent
from ..core.messages import TaskSpec
from ..tools.content import normalise_subject

MAX_CHARS = 8000
EXCERPT_FOR_MODEL = 1200

SYSTEM = (
    "You classify documents for a personal archive. "
    "Return a short lowercase subject key (2-4 words) that groups files about the same thing, "
    "plus a one-sentence summary. Never invent facts that are not in the text."
)


class DocumentAgent(BaseAgent):
    handles = ("doc.extract",)
    description = "Extracts text from documents and PDFs, then assigns a subject key."

    name = "document-agent"

    def prepare(self, task: TaskSpec) -> None:
        year = task.payload.get("year")
        self.name = f"doc-{year}" if year else "document-agent"

    async def run(self, task: TaskSpec) -> dict[str, Any]:
        paths: list[str] = task.payload["paths"]
        year = task.payload.get("year")

        texts: dict[str, str] = {}
        subjects: dict[str, str] = {}
        summaries: dict[str, str] = {}
        empty: list[str] = []

        for path in paths:
            payload = await self.ctx.call_tool(
                "read_text", {"path": path, "max_chars": MAX_CHARS}, agent=self.name
            )
            text = payload.get("text", "")
            if not text.strip():
                # Scanned PDFs land here: no text layer, nothing to classify.
                empty.append(path)
                continue
            texts[path] = text

            # 1. deterministic answer, always available
            heuristic = normalise_subject(text, path)

            # 2. ask the model to do better, with the heuristic as the fallback
            verdict = await self.ctx.llm.json(
                f"File name: {path}\n\nFirst part of the text:\n{text[:EXCERPT_FOR_MODEL]}\n\n"
                'Return {"subject": "...", "summary": "..."}',
                system=SYSTEM,
                fallback={"subject": heuristic, "summary": text.strip()[:140]},
                max_tokens=200,
            )

            # 3. check the judgement before trusting it
            subject = str(verdict.get("subject") or heuristic).strip().lower()
            if not 2 <= len(subject) <= 60:
                subject = heuristic
            subjects[path] = subject
            summaries[path] = str(verdict.get("summary", ""))[:200]

            if verdict.get("_source") != "fallback":
                self.ctx.tracer.llm(f"subject '{subject}' for {path}", source=verdict["_source"])

        await self.ctx.blackboard.merge_dict("doc_texts", texts, by=self.name)
        await self.ctx.blackboard.merge_dict("doc_subjects", subjects, by=self.name)
        await self.ctx.blackboard.merge_dict("doc_summaries", summaries, by=self.name)

        return {
            "year": year,
            "documents_read": len(paths),
            "with_text": len(texts),
            "no_text_layer": empty,
            "subjects_found": len(set(subjects.values())),
        }
