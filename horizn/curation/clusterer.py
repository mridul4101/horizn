"""Clusters photos into carousel groups using GPS proximity, time-window logic, and Gemini visual subject intelligence."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from sklearn.cluster import DBSCAN

from horizn.config import settings

logger = logging.getLogger(__name__)

_MAX_THUMB_PX = 128
_MAX_BATCH_SIZE = 16


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_dt(val: Any) -> datetime | None:
    """Return a timezone-aware datetime from a string or datetime value."""
    if val is None:
        return None
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val
    try:
        dt = datetime.fromisoformat(str(val))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _hours_between(a: datetime | None, b: datetime | None) -> float:
    """Return absolute hour difference between two datetimes (or infinity if either is None)."""
    if a is None or b is None:
        return float("inf")
    return abs((a - b).total_seconds()) / 3600.0


def _split_oversized(group: list[dict], max_slides: int) -> list[list[dict]]:
    """Split a group that exceeds max_slides into consecutive sub-groups."""
    if len(group) <= max_slides:
        return [group]
    chunks: list[list[dict]] = []
    for i in range(0, len(group), max_slides):
        chunks.append(group[i : i + max_slides])
    return chunks


def _merge_clusters_by_time(
    label_to_photos: dict[int, list[dict]],
    time_window_hours: float,
) -> list[list[dict]]:
    """Merge DBSCAN clusters whose photo time-ranges overlap within time_window_hours."""
    cluster_ids = sorted(label_to_photos.keys())
    cluster_ranges: dict[int, tuple[datetime | None, datetime | None]] = {}
    for cid in cluster_ids:
        dts = [_parse_dt(p["taken_at"]) for p in label_to_photos[cid]]
        dts = [d for d in dts if d is not None]
        if dts:
            cluster_ranges[cid] = (min(dts), max(dts))
        else:
            cluster_ranges[cid] = (None, None)

    parent = {cid: cid for cid in cluster_ids}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        parent[find(x)] = find(y)

    for i, ci in enumerate(cluster_ids):
        for cj in cluster_ids[i + 1 :]:
            min_i, max_i = cluster_ranges[ci]
            min_j, max_j = cluster_ranges[cj]
            if (
                _hours_between(min_i, max_j) <= time_window_hours
                or _hours_between(max_i, min_j) <= time_window_hours
                or _hours_between(min_i, min_j) <= time_window_hours
                or _hours_between(max_i, max_j) <= time_window_hours
            ):
                union(ci, cj)

    merged: dict[int, list[dict]] = {}
    for cid in cluster_ids:
        root = find(cid)
        merged.setdefault(root, []).extend(label_to_photos[cid])

    return list(merged.values())


# ---------------------------------------------------------------------------
# AI Visual Subject Clustering (Gemini)
# ---------------------------------------------------------------------------


def _resize_to_thumb_bytes(image_path: str) -> bytes:
    """Create a compact 128px thumbnail for fast multimodal reasoning."""
    img = Image.open(image_path).convert("RGB")
    img.thumbnail((_MAX_THUMB_PX, _MAX_THUMB_PX), Image.BILINEAR)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=65)
    return buf.getvalue()


async def _cluster_batch_with_gemini(subgroup: list[dict], max_slides: int) -> list[list[dict]]:
    """Send a batch of up to 16 photos to Gemini to group into thematic carousels."""
    if len(subgroup) <= 2:
        return [subgroup]

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.gemini_api_key)
        n = len(subgroup)

        prompt_text = (
            f"You are a professional Instagram travel and landscape curator.\n"
            f"Analyze these {n} photos (indexed 0 to {n-1}) from a travel session.\n\n"
            "Identify distinct visual themes and subjects (e.g. river/boats, temples/architecture, "
            "street scenes, night/ceremony, food/details).\n"
            "Group photos that share a cohesive visual theme into organic Instagram carousels.\n\n"
            "Rules:\n"
            f"- Each carousel should have between 2 and {max_slides} photos (typically 3 to 7 photos).\n"
            f"- Each index 0..{n-1} should be in at most one carousel.\n"
            "- Return ONLY valid JSON (no markdown fences) with format:\n"
            '{"carousels": [{"theme": "<theme description>", "indices": [0, 2, ...]}, ...]}'
        )

        parts: list[types.Part] = [types.Part.from_text(text=prompt_text)]

        for photo in subgroup:
            try:
                img_bytes = _resize_to_thumb_bytes(photo["export_path"])
                parts.append(types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"))
            except Exception as exc:
                logger.warning("Could not read thumbnail for photo: %s", exc)

        logger.info("Calling Gemini for visual subject clustering across %d photos...", n)
        response = client.models.generate_content(
            model=settings.gemini_flash_model,
            contents=[types.Content(role="user", parts=parts)],
        )

        raw = response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        data = json.loads(raw)
        carousels_spec = data.get("carousels", [])

        if not carousels_spec:
            return _split_oversized(subgroup, max_slides)

        ai_clusters: list[list[dict]] = []
        assigned_indices: set[int] = set()

        for c_spec in carousels_spec:
            indices = c_spec.get("indices", [])
            valid_indices = [i for i in indices if 0 <= i < n and i not in assigned_indices]
            if valid_indices:
                cluster_photos = [subgroup[i] for i in valid_indices]
                # Store the theme description on the photos for captioning
                theme_name = c_spec.get("theme", "")
                for p in cluster_photos:
                    p["_ai_theme"] = theme_name
                ai_clusters.extend(_split_oversized(cluster_photos, max_slides))
                assigned_indices.update(valid_indices)

        # Catch unassigned photos
        unassigned = [subgroup[i] for i in range(n) if i not in assigned_indices]
        if unassigned:
            ai_clusters.extend(_split_oversized(unassigned, max_slides))

        return ai_clusters

    except Exception as exc:
        logger.warning("Gemini visual subject clustering error (%s); falling back to slice.", exc)
        return _split_oversized(subgroup, max_slides)


async def _cluster_with_gemini(group: list[dict], max_slides: int) -> list[list[dict]]:
    """Divide large groups into manageable batches (<= 16) and cluster each with Gemini."""
    if not settings.gemini_api_key or settings.gemini_api_key.startswith("your_"):
        return _split_oversized(group, max_slides)

    # If small enough, cluster directly
    if len(group) <= _MAX_BATCH_SIZE:
        return await _cluster_batch_with_gemini(group, max_slides)

    # Otherwise, chunk into batches of 14-16 and cluster each
    all_clusters: list[list[dict]] = []
    for i in range(0, len(group), _MAX_BATCH_SIZE):
        batch = group[i : i + _MAX_BATCH_SIZE]
        clusters = await _cluster_batch_with_gemini(batch, max_slides)
        all_clusters.extend(clusters)
        await asyncio.sleep(1)  # brief pause between batches

    return all_clusters


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def cluster_photos(photos: list[dict]) -> list[list[dict]]:
    """Cluster photos into carousel-sized groups using GPS, time window, and AI visual subjects."""
    max_slides = settings.carousel_max_slides
    time_window = float(settings.cluster_time_window_hours)
    gps_radius_km = settings.cluster_gps_radius_km

    with_gps: list[dict] = []
    without_gps: list[dict] = []
    for p in photos:
        if p.get("lat") is not None and p.get("lon") is not None:
            with_gps.append(p)
        else:
            without_gps.append(p)

    spatio_temporal_groups: list[list[dict]] = []

    # 1. GPS photos – DBSCAN with haversine metric
    if with_gps:
        coords_rad = np.array(
            [[math.radians(p["lat"]), math.radians(p["lon"])] for p in with_gps]
        )
        eps_rad = gps_radius_km / 6371.0
        db = DBSCAN(eps=eps_rad, min_samples=1, algorithm="ball_tree", metric="haversine")
        labels = db.fit_predict(coords_rad)

        label_to_photos: dict[int, list[dict]] = {}
        for photo, label in zip(with_gps, labels):
            key = int(label)
            label_to_photos.setdefault(key, []).append(photo)

        merged_groups = _merge_clusters_by_time(label_to_photos, time_window)
        spatio_temporal_groups.extend(merged_groups)

    # 2. No-GPS photos – sort by taken_at, split on time gaps
    if without_gps:
        sorted_no_gps = sorted(
            without_gps,
            key=lambda p: _parse_dt(p["taken_at"]) or datetime.min.replace(tzinfo=timezone.utc),
        )

        current_group: list[dict] = [sorted_no_gps[0]]
        for prev, cur in zip(sorted_no_gps, sorted_no_gps[1:]):
            gap = _hours_between(_parse_dt(prev["taken_at"]), _parse_dt(cur["taken_at"]))
            if gap > time_window:
                spatio_temporal_groups.append(current_group)
                current_group = [cur]
            else:
                current_group.append(cur)
        spatio_temporal_groups.append(current_group)

    # 3. Apply Gemini Visual Subject Clustering on each spatio-temporal group
    final_carousels: list[list[dict]] = []
    for group in spatio_temporal_groups:
        if len(group) > 2 and settings.gemini_api_key and not settings.gemini_api_key.startswith("your_"):
            thematic_clusters = await _cluster_with_gemini(group, max_slides)
            final_carousels.extend(thematic_clusters)
        else:
            final_carousels.extend(_split_oversized(group, max_slides))

    return final_carousels
