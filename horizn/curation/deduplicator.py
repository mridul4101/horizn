"""Removes near-duplicate photos within a cluster using perceptual hashing."""

from __future__ import annotations

from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

import imagehash
from PIL import Image

from horizn.config import settings


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


def _parse_time(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val))
    except Exception:
        return None


def _resolve_image_path(p: dict) -> Path | None:
    """Resolve the photo's image file from export_path or filepath."""
    for key in ("export_path", "filepath"):
        raw = p.get(key)
        if not raw:
            continue
        path = Path(raw)
        if path.exists():
            return path
        try:
            alt = Path(settings.export_dir) / path.name
            if alt.exists():
                return alt
        except Exception:
            pass
    return None


def deduplicate_candidates(
    photos: list[dict],
    hamming_threshold: int = 8,
    burst_threshold: int = 12,
    burst_time_window_seconds: float = 900.0,
) -> tuple[list[dict], dict[str, list[str]]]:
    """Globally deduplicate uncurated candidate photos across a session.

    Groups near-identical photos using perceptual hashing (pHash) and time proximity.
    For each component:
    1. Selects the single sharpest photo as the 'Hero Shot'.
    2. Maps the remaining duplicate photo IDs to the Hero Shot:
       { hero_id: [duplicate_id1, duplicate_id2, ...] }

    Parameters
    ----------
    photos:
        List of photo dicts containing 'id', 'export_path', 'sharpness', and optionally 'taken_at'.
    hamming_threshold:
        Maximum Hamming distance to consider photos near-identical regardless of time (default 8).
    burst_threshold:
        Maximum Hamming distance to consider photos duplicates when taken within burst_time_window_seconds (default 12).
    burst_time_window_seconds:
        Time window in seconds (default 900s = 15 minutes) for burst/bracketing matching.

    Returns
    -------
    tuple[list[dict], dict[str, list[str]]]:
        (hero_photos, duplicate_map)
    """
    if not photos:
        return [], {}

    hashes: list[imagehash.ImageHash | None] = []
    dts: list[datetime | None] = []
    for p in photos:
        resolved = _resolve_image_path(p)
        if resolved:
            try:
                img = Image.open(resolved)
                hashes.append(imagehash.phash(img))
            except Exception:
                hashes.append(None)
        else:
            hashes.append(None)
        dts.append(_parse_time(p.get("taken_at")))

    n = len(photos)
    uf = _UnionFind(n)

    for i in range(n):
        if hashes[i] is None:
            continue
        for j in range(i + 1, n):
            if hashes[j] is None:
                continue
            dist = hashes[i] - hashes[j]
            is_match = False
            if dist <= hamming_threshold:
                is_match = True
            elif dist <= burst_threshold and dts[i] and dts[j]:
                sec_diff = abs((dts[i] - dts[j]).total_seconds())
                if sec_diff <= burst_time_window_seconds:
                    is_match = True

            if is_match:
                uf.union(i, j)

    components: dict[int, list[int]] = {}
    for idx in range(n):
        root = uf.find(idx)
        components.setdefault(root, []).append(idx)

    hero_indices: list[int] = []
    duplicate_map: dict[str, list[str]] = {}

    for indices in components.values():
        best_idx = max(
            indices,
            key=lambda i: (photos[i].get("sharpness") or 0.0, str(photos[i].get("id"))),
        )
        hero_indices.append(best_idx)
        hero_id = photos[best_idx]["id"]
        dups = [photos[i]["id"] for i in indices if i != best_idx]
        if dups:
            duplicate_map[hero_id] = dups

    # Preserve original order for heroes
    hero_set = set(hero_indices)
    heroes = [p for i, p in enumerate(photos) if i in hero_set]
    return heroes, duplicate_map


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
        resolved = _resolve_image_path(p)
        if resolved:
            try:
                img = Image.open(resolved)
                hashes.append(imagehash.phash(img))
            except Exception:
                hashes.append(None)
        else:
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
