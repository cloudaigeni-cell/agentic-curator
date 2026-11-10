"""Text similarity without a model.

The duplicate-finder uses the LLM for *judgement* ("are these about the same
subject?") but never for *measurement*. Measurement is done here, with shingles
and Jaccard similarity, because:

  * it is deterministic — the same inputs always give the same number
  * it is auditable — a reviewer can recompute it
  * it is free — no token cost on a library with 10,000 files

A good rule for agentic systems: let the model decide, let code measure.
"""

from __future__ import annotations

import re

_WORD = re.compile(r"[a-z0-9]+")


def shingles(text: str, *, k: int = 5) -> set[str]:
    """Overlapping k-word windows. Captures word order, unlike a bag of words."""
    words = _WORD.findall(text.lower())
    if len(words) < k:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i : i + k]) for i in range(len(words) - k + 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    """|intersection| / |union|. 1.0 = identical shingle sets, 0.0 = nothing shared."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def text_similarity(text_a: str, text_b: str, *, k: int = 5) -> float:
    return jaccard(shingles(text_a, k=k), shingles(text_b, k=k))


def group_by_similarity(
    texts: dict[str, str], *, threshold: float = 0.80, k: int = 5
) -> list[dict]:
    """Cluster paths whose text is at least `threshold` similar.

    Returns dicts carrying the pairwise scores, because a bare cluster is not
    evidence — the scores are what a human (or the policy gate) reviews.
    """
    paths = list(texts)
    sets = {p: shingles(texts[p], k=k) for p in paths}
    parent = {p: p for p in paths}
    scores: dict[tuple[str, str], float] = {}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, left in enumerate(paths):
        for right in paths[i + 1 :]:
            score = jaccard(sets[left], sets[right])
            if score >= threshold:
                scores[(left, right)] = round(score, 4)
                ra, rb = find(left), find(right)
                if ra != rb:
                    parent[rb] = ra

    clusters: dict[str, list[str]] = {}
    for path in paths:
        clusters.setdefault(find(path), []).append(path)

    out = []
    for members in clusters.values():
        if len(members) < 2:
            continue
        members = sorted(members)
        pair_scores = {
            f"{a} ~ {b}": s
            for (a, b), s in scores.items()
            if a in members and b in members
        }
        out.append(
            {
                "members": members,
                "pair_scores": pair_scores,
                "min_score": min(pair_scores.values()) if pair_scores else 0.0,
            }
        )
    return out
