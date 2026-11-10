"""Deterministic helpers shared by the MCP server and the tests."""

from .content import classify, extract_text, normalise_subject, sha256_file, year_hint
from .imaging import cluster, dhash, hamming, similarity
from .similarity import group_by_similarity, jaccard, shingles, text_similarity

__all__ = [
    "classify",
    "cluster",
    "dhash",
    "extract_text",
    "group_by_similarity",
    "hamming",
    "jaccard",
    "normalise_subject",
    "sha256_file",
    "shingles",
    "similarity",
    "text_similarity",
    "year_hint",
]
