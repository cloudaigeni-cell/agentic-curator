"""The deterministic layer. If these fail, no agent can be trusted."""

from pathlib import Path

from agentic_curator.sample import _photo
from agentic_curator.tools import (
    cluster,
    dhash,
    group_by_similarity,
    hamming,
    normalise_subject,
    sha256_file,
    text_similarity,
    year_hint,
)


def test_sha256_identical_and_different(tmp_path: Path) -> None:
    a, b, c = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    a.write_text("same")
    b.write_text("same")
    c.write_text("different")
    assert sha256_file(a) == sha256_file(b) != sha256_file(c)


def test_year_prefers_filename_over_mtime() -> None:
    assert year_hint(Path("IMG_20190704_beach.jpg"), 1_800_000_000) == 2019
    assert year_hint(Path("notes.txt"), 1_577_900_000) == 2020


def test_subject_ignores_versions_months_and_years() -> None:
    a = normalise_subject("", "meeting_notes_2022_jan.txt")
    b = normalise_subject("", "meeting_notes_2022_feb.txt")
    c = normalise_subject("", "migration_notes_2021_v2.txt")
    assert a == b == "meeting notes"
    assert c == "migration notes"


def test_text_similarity_bounds() -> None:
    base = "the quick brown fox jumps over the lazy dog near the quiet river bank today"
    assert text_similarity(base, base) == 1.0
    assert text_similarity(base, "completely unrelated words about something else entirely ok") == 0.0
    assert 0.3 < text_similarity(base, base.replace("quiet", "noisy")) < 1.0


def test_group_by_similarity_returns_evidence() -> None:
    text = " ".join(f"word{i}" for i in range(60))
    groups = group_by_similarity(
        {"a": text, "b": text + " extra", "c": "nothing in common here at all friend"},
        threshold=0.8,
    )
    assert len(groups) == 1
    assert groups[0]["members"] == ["a", "b"]
    assert groups[0]["min_score"] >= 0.8


def test_dhash_survives_reencode_and_resize(tmp_path: Path) -> None:
    original, recompressed, small, other = (tmp_path / n for n in ("o.jpg", "r.jpg", "s.jpg", "x.jpg"))
    _photo(original, seed=11, quality=95)
    _photo(recompressed, seed=11, quality=55)
    _photo(small, seed=11, size=(320, 240))
    _photo(other, seed=12)
    h = {p.name: dhash(p) for p in (original, recompressed, small, other)}
    assert hamming(h["o.jpg"], h["r.jpg"]) <= 4
    assert hamming(h["o.jpg"], h["s.jpg"]) <= 4
    assert hamming(h["o.jpg"], h["x.jpg"]) > 10
    assert cluster(h, threshold=4) == [["o.jpg", "r.jpg", "s.jpg"]]


def test_dhash_rejects_non_images(tmp_path: Path) -> None:
    fake = tmp_path / "not.jpg"
    fake.write_text("this is not an image")
    assert dhash(fake) is None
