"""Removes near-duplicate photos within a cluster using perceptual hashing."""

from __future__ import annotations

from collections import deque

import imagehash
from PIL import Image


# ---------------------------------------------------------------------------
# Union-Find (path-compression + rank)
# ---------------------------------------------------------------------------


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, x: int, y: int) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        if self.rank[rx] < self.rank[ry]:
            rx, ry = ry, rx
        self.parent[ry] = rx
        if self.rank[rx] == self.rank[ry]:
            self.rank[rx] += 1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_HAMMING_THRESHOLD = 8


def deduplicate_cluster(photos: list[dict]) -> list[dict]:
    """
    Remove near-duplicate photos from a cluster using perceptual hashing.

    For each connected component in the similarity graph (edge when Hamming
    distance ≤ 8), keep only the photo with the highest sharpness score.
    Original order of survivors is preserved.

    Parameters
    ----------
    photos:
        List of photo dicts containing at least ``export_path`` and
        ``sharpness`` keys.

    Returns
    -------
    Deduplicated list of photo dicts in their original relative order.
    """
    if not photos:
        return []

    # Compute pHash for each photo; fall back gracefully on IO errors.
    hashes: list[imagehash.ImageHash | None] = []
    for p in photos:
        try:
            img = Image.open(p["export_path"])
            hashes.append(imagehash.phash(img))
        except Exception:
            hashes.append(None)

    n = len(photos)
    uf = _UnionFind(n)

    for i in range(n):
        if hashes[i] is None:
            continue
        for j in range(i + 1, n):
            if hashes[j] is None:
                continue
            dist = hashes[i] - hashes[j]
            if dist <= _HAMMING_THRESHOLD:
                uf.union(i, j)

    # Group indices by component root
    components: dict[int, list[int]] = {}
    for idx in range(n):
        root = uf.find(idx)
        components.setdefault(root, []).append(idx)

    # From each component pick the sharpest photo
    survivors: set[int] = set()
    for indices in components.values():
        best_idx = max(
            indices,
            key=lambda i: photos[i].get("sharpness") or 0.0,
        )
        survivors.add(best_idx)

    # Return in original order
    return [p for i, p in enumerate(photos) if i in survivors]
