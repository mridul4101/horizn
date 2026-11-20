"""Determines and enforces a consistent aspect ratio for all slides in a carousel."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


# ---------------------------------------------------------------------------
# Bucket → target pixel dimensions
# ---------------------------------------------------------------------------

_BUCKET_DIMS: dict[str, tuple[int, int]] = {
    "4:5": (1080, 1350),
    "1:1": (1080, 1080),
    "16:9": (1080, 608),
    "portrait": (1080, 1350),
    "landscape-wide": (1080, 608),
}

# Fallback when the bucket is unrecognised
_DEFAULT_DIMS = (1080, 1080)


def _target_dims(bucket: str) -> tuple[int, int]:
    return _BUCKET_DIMS.get(bucket, _DEFAULT_DIMS)


def _majority_bucket(photos: list[dict]) -> str:
    """Return the most common aspect_ratio value across the photo list."""
    counts: dict[str, int] = {}
    for p in photos:
        bucket = p.get("aspect_ratio") or ""
        counts[bucket] = counts.get(bucket, 0) + 1
    if not counts:
        return ""
    return max(counts, key=lambda k: counts[k])


def _letterbox(image: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """
    Fit *image* into (target_w × target_h) with centre-aligned letterboxing
    (black padding).  The image is never upscaled beyond its original size.
    """
    src_w, src_h = image.size
    scale = min(target_w / src_w, target_h / src_h)
    new_w = int(src_w * scale)
    new_h = int(src_h * scale)
    resized = image.resize((new_w, new_h), Image.LANCZOS)

    canvas = Image.new("RGB", (target_w, target_h), (0, 0, 0))
    paste_x = (target_w - new_w) // 2
    paste_y = (target_h - new_h) // 2
    # Drop alpha channel if present before pasting
    if resized.mode in ("RGBA", "LA"):
        canvas.paste(resized, (paste_x, paste_y), resized)
    else:
        canvas.paste(resized.convert("RGB"), (paste_x, paste_y))
    return canvas


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def align_aspect_ratios(photos: list[dict], export_dir: Path) -> list[dict]:
    """
    Pad minority-aspect-ratio photos so every slide shares the majority bucket.

    For each photo whose ``aspect_ratio`` differs from the majority, the image
    is letterboxed (black bars) to the target pixel dimensions and saved as
    ``{photo_id}_padded.jpg`` in *export_dir*.  The photo dict's
    ``export_path`` is updated in-place and the updated list is returned.

    Parameters
    ----------
    photos:
        List of photo dicts with keys: id, aspect_ratio, export_path.
    export_dir:
        Directory to write padded JPEG files.

    Returns
    -------
    Updated photos list (same objects, some with modified export_path).
    """
    if not photos:
        return photos

    export_dir = Path(export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)

    majority = _majority_bucket(photos)
    target_w, target_h = _target_dims(majority)

    updated: list[dict] = []
    for photo in photos:
        bucket = photo.get("aspect_ratio") or ""
        if bucket == majority:
            updated.append(photo)
            continue

        # This photo is a minority – letterbox it
        try:
            img = Image.open(photo["export_path"]).convert("RGB")
            padded = _letterbox(img, target_w, target_h)

            padded_path = export_dir / f"{photo['id']}_padded.jpg"
            padded.save(str(padded_path), format="JPEG", quality=92)

            photo = dict(photo)  # shallow copy to avoid mutating caller's dict
            photo["export_path"] = str(padded_path)
        except Exception:
            # If anything goes wrong, leave the photo untouched
            pass

        updated.append(photo)

    return updated
