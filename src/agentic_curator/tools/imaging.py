"""Perceptual hashing for photos.

Why not sha256? Because two photos of the same moment are never byte-identical
— different compression, a resize, a thumbnail. A cryptographic hash answers
"are these the same bytes"; a *perceptual* hash answers "do these look the
same", which is the question a photo de-duplicator actually has.

dHash (difference hash), 64 bits:
    1. shrink to 9x8 greyscale  -> throws away colour and detail
    2. compare each pixel with its right-hand neighbour -> 8x8 = 64 booleans
    3. pack to 16 hex characters

Two images are "the same shot" when their hashes differ in few bits. Hamming
distance 0-4 is effectively identical; 5-10 is the same scene a moment apart;
above that they are different pictures.
"""

from __future__ import annotations

from pathlib import Path

HASH_SIZE = 8
NEAR_DUPLICATE_BITS = 4  # <= this many differing bits => treat as the same shot
SIMILAR_BITS = 10


def dhash(path: Path, *, hash_size: int = HASH_SIZE) -> str | None:
    """Return a 16-char hex fingerprint, or None if the file is not a readable image."""
    try:
        from PIL import Image, ImageOps
    except ImportError:  # pragma: no cover
        return None
    try:
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img)  # a rotated copy is the same photo
            img = img.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
            pixels = list(img.tobytes())  # mode "L": one byte per pixel
    except Exception:  # noqa: BLE001 - unreadable image is data, not a crash
        return None

    bits = 0
    index = 0
    for row in range(hash_size):
        offset = row * (hash_size + 1)
        for col in range(hash_size):
            if pixels[offset + col] > pixels[offset + col + 1]:
                bits |= 1 << index
            index += 1
    return f"{bits:0{hash_size * hash_size // 4}x}"


def image_size(path: Path) -> tuple[int, int] | None:
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover
        return None
    try:
        with Image.open(path) as img:
            return img.size
    except Exception:  # noqa: BLE001
        return None


def hamming(hash_a: str, hash_b: str) -> int:
    """Number of differing bits. 0 means the fingerprints are identical."""
    if len(hash_a) != len(hash_b):
        raise ValueError("cannot compare hashes of different lengths")
    return bin(int(hash_a, 16) ^ int(hash_b, 16)).count("1")


def similarity(hash_a: str, hash_b: str) -> float:
    """0.0 - 1.0, where 1.0 is an identical fingerprint. Handy for confidence scores."""
    bits = len(hash_a) * 4
    return 1.0 - (hamming(hash_a, hash_b) / bits)


def cluster(hashes: dict[str, str], *, threshold: int = NEAR_DUPLICATE_BITS) -> list[list[str]]:
    """Group paths whose fingerprints are within `threshold` bits.

    Single-link clustering via union-find: A~B and B~C puts A, B and C in one
    group even if A and C are slightly further apart. That is the right
    behaviour for burst shots, which form a chain of small differences.
    """
    paths = list(hashes)
    parent = {p: p for p in paths}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i, left in enumerate(paths):
        for right in paths[i + 1 :]:
            if hamming(hashes[left], hashes[right]) <= threshold:
                union(left, right)

    groups: dict[str, list[str]] = {}
    for path in paths:
        groups.setdefault(find(path), []).append(path)
    return [sorted(members) for members in groups.values() if len(members) > 1]
