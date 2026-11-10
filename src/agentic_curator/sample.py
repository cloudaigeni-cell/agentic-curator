"""Builds a small, deliberately messy library so there is something to curate.

Every kind of mess the agents are designed to find is planted here on purpose,
and `EXPECTED` records what a correct run should report. That makes the demo a
test: if the numbers in your report differ, something is wrong.
"""

from __future__ import annotations

import os
import random
import time
from pathlib import Path

EXPECTED = {
    "exact_document_groups": 2,  # invoice copy + pdf copy
    "near_document_groups": 1,  # the two migration notes
    "photo_duplicate_groups": 2,  # beach re-encode, city resize
    "photo_review_groups": 1,  # two frames of the same scene
    "merged_subjects": 2,  # migration notes, meeting notes
}


def _stamp(path: Path, year: int, month: int = 6, day: int = 15) -> None:
    moment = time.mktime((year, month, day, 12, 0, 0, 0, 0, -1))
    os.utime(path, (moment, moment))


def _pdf(path: Path, lines: list[str]) -> None:
    """A minimal valid one-page PDF with a text layer — no extra dependency."""
    text_ops = ["BT", "/F1 12 Tf", "72 720 Td", "14 TL"]
    for line in lines:
        safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        text_ops.append(f"({safe}) Tj T*")
    text_ops.append("ET")
    stream = "\n".join(text_ops).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))


def _photo(path: Path, seed: int, size: tuple[int, int] = (640, 480), shift: int = 0,
           quality: int = 90) -> None:
    """A synthetic 'photo': smooth gradients plus a few shapes, unique per seed."""
    from PIL import Image, ImageDraw, ImageFilter

    rng = random.Random(seed)
    base = Image.new("RGB", (640, 480))
    draw = ImageDraw.Draw(base)
    top = tuple(rng.randint(40, 220) for _ in range(3))
    bottom = tuple(rng.randint(40, 220) for _ in range(3))
    for y in range(480):
        mix = y / 479
        draw.line(
            [(0, y), (640, y)],
            fill=tuple(int(top[i] * (1 - mix) + bottom[i] * mix) for i in range(3)),
        )
    for _ in range(7):
        x, y = rng.randint(0, 560), rng.randint(0, 400)
        w, h = rng.randint(50, 200), rng.randint(50, 200)
        colour = tuple(rng.randint(0, 255) for _ in range(3))
        draw.ellipse([x + shift, y, x + w + shift, y + h], fill=colour)
    base = base.filter(ImageFilter.GaussianBlur(3))
    if size != (640, 480):
        base = base.resize(size)
    path.parent.mkdir(parents=True, exist_ok=True)
    base.save(path, quality=quality)


MIGRATION = """Database migration notes

We are moving the customer database from the old cluster to the new managed
service. The cutover window is Saturday night. Steps: freeze writes, take a
final snapshot, restore into the new service, run the row count comparison,
switch the connection string, and unfreeze. Rollback is to point the
connection string back at the old cluster, which stays read-only for a week.
Open questions: who signs off the row counts, and whether reporting jobs need
the old replica during the freeze.
"""

MEETING_A = """Weekly meeting notes

Attendees: platform team. Agenda: storage costs, on-call rota, the backup test.
Storage costs rose because of the unpruned snapshots; action is to add a
ninety day retention rule. The on-call rota moves to a two week rotation from
next month. The backup restore test passed for the primary but not the replica.
"""

MEETING_B = """Weekly meeting notes

Attendees: platform team and finance. Agenda: budget for next quarter, the
vendor renewal, hiring. The vendor renewal is approved for one year only.
Finance asked for a monthly cost report. One backfill hire is approved.
"""


def build_sample_library(root: Path) -> dict[str, int]:
    root = Path(root)
    (root / "documents").mkdir(parents=True, exist_ok=True)
    (root / "photos").mkdir(parents=True, exist_ok=True)
    (root / "downloads").mkdir(parents=True, exist_ok=True)

    docs = root / "documents"
    # --- exact duplicate text -------------------------------------------
    invoice = "Invoice 4471\nConsulting services, March.\nTotal due: 1,250.00\nPayment terms: 30 days.\n" * 6
    (docs / "invoice_2019_march.txt").write_text(invoice)
    (root / "downloads" / "invoice_2019_march (1).txt").write_text(invoice)
    _stamp(docs / "invoice_2019_march.txt", 2019, 3)
    _stamp(root / "downloads" / "invoice_2019_march (1).txt", 2019, 4)

    # --- exact duplicate PDF --------------------------------------------
    pdf_lines = ["Service agreement 2020", "This agreement covers support and maintenance.",
                 "Term: twelve months from the start date.", "Either party may end it with notice."]
    _pdf(docs / "service_agreement_2020.pdf", pdf_lines)
    (root / "downloads" / "service_agreement_2020_copy.pdf").write_bytes(
        (docs / "service_agreement_2020.pdf").read_bytes()
    )
    _stamp(docs / "service_agreement_2020.pdf", 2020, 2)
    _stamp(root / "downloads" / "service_agreement_2020_copy.pdf", 2020, 5)

    # --- near-identical: same notes, one line changed -------------------
    (docs / "migration_notes_2021.txt").write_text(MIGRATION)
    (docs / "migration_notes_2021_v2.txt").write_text(
        MIGRATION.replace("Saturday night", "Sunday night") + "Update: window moved by one day.\n"
    )
    _stamp(docs / "migration_notes_2021.txt", 2021, 9, 1)
    _stamp(docs / "migration_notes_2021_v2.txt", 2021, 9, 3)

    # --- same subject, different content (merge candidates) -------------
    (docs / "meeting_notes_2022_jan.txt").write_text(MEETING_A)
    (docs / "meeting_notes_2022_feb.txt").write_text(MEETING_B)
    _stamp(docs / "meeting_notes_2022_jan.txt", 2022, 1)
    _stamp(docs / "meeting_notes_2022_feb.txt", 2022, 2)

    # --- unique documents that must survive ------------------------------
    (docs / "recipe_bread_2020.md").write_text(
        "# Bread\n\nFlour, water, salt, yeast. Mix, rest overnight, shape, bake hot.\n"
    )
    _pdf(docs / "tax_summary_2021.pdf", ["Tax summary 2021", "Income and deductions for the year.",
                                         "Keep this for seven years."])
    _stamp(docs / "recipe_bread_2020.md", 2020, 11)
    _stamp(docs / "tax_summary_2021.pdf", 2021, 4)

    photos = root / "photos"
    # --- beach: original + re-encoded copy (same shot) -------------------
    _photo(photos / "IMG_20190704_beach.jpg", seed=1, quality=95)
    _photo(photos / "IMG_20190704_beach_whatsapp.jpg", seed=1, quality=60)
    # --- city: original + downsized copy (same shot) ---------------------
    _photo(photos / "IMG_20200815_city.jpg", seed=2, quality=92)
    _photo(photos / "IMG_20200815_city_small.jpg", seed=2, size=(320, 240), quality=85)
    # --- same scene, a moment later (must NOT be deleted) ----------------
    _photo(photos / "IMG_20210321_park_1.jpg", seed=3)
    _photo(photos / "IMG_20210321_park_2.jpg", seed=3, shift=14)
    # --- unique photos ---------------------------------------------------
    _photo(photos / "IMG_20220610_mountain.jpg", seed=4)
    _photo(photos / "IMG_20220611_lake.jpg", seed=5)
    for name, year in [
        ("IMG_20190704_beach.jpg", 2019), ("IMG_20190704_beach_whatsapp.jpg", 2019),
        ("IMG_20200815_city.jpg", 2020), ("IMG_20200815_city_small.jpg", 2020),
        ("IMG_20210321_park_1.jpg", 2021), ("IMG_20210321_park_2.jpg", 2021),
        ("IMG_20220610_mountain.jpg", 2022), ("IMG_20220611_lake.jpg", 2022),
    ]:
        _stamp(photos / name, year)

    files = [p for p in root.rglob("*") if p.is_file()]
    return {"files": len(files), "bytes": sum(p.stat().st_size for p in files)}
