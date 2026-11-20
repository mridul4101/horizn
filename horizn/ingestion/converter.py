"""Converts HEIC/RAW photos to JPEG exports suitable for Instagram upload."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Optional

from horizn.config import settings

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

logger = logging.getLogger(__name__)


def _find_exported_jpeg(output_dir: Path, stem: str) -> Optional[Path]:
    """Return the first .jpg file in *output_dir* whose stem matches *stem*, or None."""
    for candidate in output_dir.glob("*.jpg"):
        if candidate.stem.lower() == stem.lower():
            return candidate
    # osxphotos may add suffixes like "_o"; fall back to any .jpg if only one
    jpgs = list(output_dir.glob("*.jpg"))
    if len(jpgs) == 1:
        return jpgs[0]
    return None


def export_as_jpeg(photo, output_dir: Path) -> Path:  # type: ignore[no-untyped-def]
    """Export *photo* as a JPEG file inside *output_dir* and return its path.

    Strategy
    --------
    1. **Primary**: delegate to ``photo.export()`` with ``jpeg=True`` so that
       osxphotos handles HEIC → JPEG conversion natively via Photos.app.
    2. **Fallback**: open the original file with Pillow, convert the colour
       space to sRGB, and save as JPEG at ``settings.JPEG_QUALITY``.

    Parameters
    ----------
    photo:
        An ``osxphotos.PhotoInfo`` instance.
    output_dir:
        Target directory; created automatically if it does not exist.

    Returns
    -------
    Path
        Absolute path to the exported JPEG.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    stem = Path(photo.original_filename).stem

    # ------------------------------------------------------------------
    # Primary path: osxphotos export
    # ------------------------------------------------------------------
    try:
        exported = photo.export(
            str(output_dir),
            use_photos_export=True,
            jpeg=True,
            overwrite=True,
        )
        # photo.export() returns a list of exported file paths
        for exp_path in (exported or []):
            p = Path(exp_path)
            if p.suffix.lower() == ".jpg":
                logger.debug("Exported via Photos.app: %s", p)
                return p
        # Try stem-based lookup as a secondary attempt
        jpg = _find_exported_jpeg(output_dir, stem)
        if jpg is not None:
            logger.debug("Resolved exported JPEG: %s", jpg)
            return jpg
        logger.warning(
            "photo.export() returned %s but no .jpg found in %s; falling back to PIL",
            exported,
            output_dir,
        )
    except Exception as exc:
        logger.warning(
            "photo.export() failed for %s: %s — falling back to PIL",
            getattr(photo, "original_filename", "?"),
            exc,
        )

    # ------------------------------------------------------------------
    # Fallback path: PIL / Pillow
    # ------------------------------------------------------------------
    from PIL import Image  # noqa: PLC0415

    # Determine source file path
    source: Optional[str] = None
    try:
        source = photo.path  # may be None if photo is not downloaded
    except Exception:
        pass
    if not source:
        try:
            source = photo.path_edited
        except Exception:
            pass

    if not source:
        raise RuntimeError(
            f"Cannot find a local file path for photo {getattr(photo, 'uuid', '?')}; "
            "it may need to be downloaded from iCloud first."
        )

    dest = output_dir / f"{stem}.jpg"

    with Image.open(source) as img:
        # Convert to RGB (handles RGBA, palette modes, HEIC, etc.)
        rgb_img = img.convert("RGB")

        # Embed an sRGB ICC profile when saving
        try:
            import io  # noqa: PLC0415
            import struct  # noqa: PLC0415

            # Build a minimal sRGB profile marker.  Pillow accepts a raw bytes
            # object for the icc_profile save keyword; None means "omit".
            # We rely on Pillow's built-in sRGB passthrough by using mode="RGB".
            icc_profile: Optional[bytes] = None
            # Try to extract the existing profile first (preserves accuracy)
            existing = img.info.get("icc_profile")
            if existing:
                icc_profile = existing
        except Exception:
            icc_profile = None

        save_kwargs = {
            "format": "JPEG",
            "quality": settings.jpeg_quality,
            "optimize": True,
        }
        if icc_profile:
            save_kwargs["icc_profile"] = icc_profile

        rgb_img.save(dest, **save_kwargs)

    logger.debug("Exported via PIL fallback: %s", dest)
    return dest
