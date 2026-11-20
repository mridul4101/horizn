"""Extracts EXIF metadata (GPS, timestamp, sharpness, aspect ratio) from photo files."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

import cv2
import numpy as np
from PIL import ExifTags

logger = logging.getLogger(__name__)

# Aspect ratio buckets: (width/height threshold ranges) → label
_ASPECT_BUCKETS = [
    (0.0, 0.85, "portrait"),
    (0.85, 0.95, "4:5"),
    (0.95, 1.10, "1:1"),
    (1.10, 2.00, "landscape-wide"),
    (2.00, float("inf"), "landscape-wide"),
]


def _bucket_aspect_ratio(ratio: float) -> str:
    """Map a float width/height ratio to its named Instagram-friendly bucket."""
    for lo, hi, label in _ASPECT_BUCKETS:
        if lo <= ratio < hi:
            return label
    return "landscape-wide"


def _compute_sharpness(pil_img) -> Optional[float]:
    """Return Laplacian variance (higher = sharper) or None on error."""
    try:
        img_array = np.array(pil_img.convert("L"))
        lap = cv2.Laplacian(img_array, cv2.CV_64F)
        return float(lap.var())
    except Exception as exc:
        logger.warning("Could not compute sharpness: %s", exc)
        return None


def extract_metadata(photo: Any, pil_img: Any) -> Dict[str, Any]:
    """Extract and return a metadata dict matching the *photos* table schema.

    Works for both Apple Photos (PhotoInfo objects) and raw local files (photo=None).
    """
    lat: Optional[float] = None
    lon: Optional[float] = None
    taken_at: Optional[datetime] = None

    # 1. From osxphotos if available
    if photo is not None:
        try:
            location = getattr(photo, "location", None)
            if location is not None:
                lat, lon = location
        except Exception:
            pass

        try:
            taken_at = getattr(photo, "date", None)
        except Exception:
            pass

    # 2. From PIL EXIF (for local directory files)
    if pil_img is not None:
        try:
            exif = pil_img.getexif()
            if exif:
                # Read timestamp
                if taken_at is None:
                    for tag_id, val in exif.items():
                        tag_name = ExifTags.TAGS.get(tag_id, tag_id)
                        if tag_name in ("DateTimeOriginal", "DateTime", "DateTimeDigitized"):
                            try:
                                taken_at = datetime.strptime(str(val), "%Y:%m:%d %H:%M:%S")
                                break
                            except Exception:
                                pass

                # Read GPS IFD if present
                if lat is None or lon is None:
                    try:
                        # 0x8825 is GPSInfo tag
                        gps_info = exif.get_ifd(0x8825) if hasattr(exif, "get_ifd") else None
                        if gps_info:
                            def _to_deg(val):
                                return float(val[0]) / float(val[1]) if isinstance(val, (tuple, list)) else float(val)

                            lat_val = gps_info.get(2)
                            lat_ref = gps_info.get(1, "N")
                            lon_val = gps_info.get(4)
                            lon_ref = gps_info.get(3, "E")
                            if lat_val and lon_val:
                                lat = _to_deg(lat_val[0]) + _to_deg(lat_val[1])/60.0 + _to_deg(lat_val[2])/3600.0
                                if lat_ref == "S": lat = -lat
                                lon = _to_deg(lon_val[0]) + _to_deg(lon_val[1])/60.0 + _to_deg(lon_val[2])/3600.0
                                if lon_ref == "W": lon = -lon
                    except Exception:
                        pass
        except Exception:
            pass

    # 3. Sharpness
    sharpness = _compute_sharpness(pil_img) if pil_img is not None else 100.0

    # 4. Aspect ratio
    aspect_ratio: str = "landscape-wide"
    if pil_img is not None:
        try:
            width, height = pil_img.size
            if height > 0:
                ratio = width / height
                aspect_ratio = _bucket_aspect_ratio(ratio)
        except Exception as exc:
            logger.warning("Could not compute aspect ratio: %s", exc)

    return {
        "taken_at": taken_at,
        "lat": lat,
        "lon": lon,
        "sharpness": sharpness,
        "aspect_ratio": aspect_ratio,
        "is_landscape": True,
    }
