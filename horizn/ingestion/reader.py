"""Reads photos from the Apple Photos library (or an album / local folder) using osxphotos and Pillow."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, Optional

import aiosqlite
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from horizn.config import settings
from horizn.database import get_db
from horizn.ingestion import converter, exif_extractor, privacy_filter

logger = logging.getLogger(__name__)


async def _get_existing_ids() -> set[str]:
    """Return the set of photo UUIDs or hashes already stored in the photos table."""
    existing: set[str] = set()
    try:
        async with get_db() as conn:
            async with conn.execute("SELECT id FROM photos") as cursor:
                async for row in cursor:
                    existing.add(row["id"])
    except Exception as exc:
        logger.warning("Could not query existing photo IDs: %s", exc)
    return existing


async def scan_local_directory(folder_path: Path) -> AsyncGenerator[Dict[str, Any], None]:
    """Scan a raw local filesystem directory for photos (HEIC, JPG, JPEG, PNG)."""
    import hashlib
    from PIL import Image, ExifTags

    existing_ids = await _get_existing_ids()
    folder = folder_path.expanduser()
    if not folder.is_dir():
        logger.warning("Local photos folder %s does not exist", folder)
        return

    supported_exts = {".heic", ".jpg", ".jpeg", ".png", ".webp"}
    files = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in supported_exts]
    logger.info("Found %d image files in local directory %s", len(files), folder)

    for fpath in files:
        file_id = hashlib.md5(fpath.name.encode()).hexdigest()
        if file_id in existing_ids:
            continue

        taken_at = None
        lat, lon = None, None

        try:
            with Image.open(fpath) as img:
                exif_raw = img.getexif()
                if exif_raw:
                    for tag_id, value in exif_raw.items():
                        tag_name = ExifTags.TAGS.get(tag_id, tag_id)
                        if tag_name == "DateTimeOriginal" or tag_name == "DateTime":
                            try:
                                taken_at = datetime.strptime(str(value), "%Y:%m:%d %H:%M:%S")
                            except Exception:
                                pass
        except Exception:
            pass

        if not taken_at:
            taken_at = datetime.fromtimestamp(fpath.stat().st_mtime)

        yield {
            "id": file_id,
            "original_filename": fpath.name,
            "path": str(fpath),
            "date": taken_at,
            "lat": lat,
            "lon": lon,
            "_is_local_file": True,
            "_photo_obj": None,
        }


async def scan_library(
    batch_start: datetime,
    batch_end: datetime,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Async generator yielding photo metadata dicts for each eligible photo.

    Supports:
    1. Local folder if `settings.local_photos_dir` is set.
    2. Specific Apple Photos Album if `settings.photos_album_name` is set.
    3. Full Apple Photos library filtered by date range.
    """
    if settings.local_photos_dir:
        async for item in scan_local_directory(settings.local_photos_dir):
            yield item
        return

    import osxphotos  # macOS only

    library_path = str(settings.photos_library_path.expanduser())
    logger.info("Opening Photos library at %s", library_path)

    loop = asyncio.get_event_loop()
    db = await loop.run_in_executor(None, lambda: osxphotos.PhotosDB(dbfile=library_path))

    # Check if user specified a dedicated album
    if settings.photos_album_name:
        logger.info("Filtering for Photos album: '%s'", settings.photos_album_name)
        all_photos = await loop.run_in_executor(
            None, lambda: db.photos(albums=[settings.photos_album_name])
        )
    else:
        all_photos = await loop.run_in_executor(None, db.photos)

    existing_ids = await _get_existing_ids()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task("Scanning library…", total=len(all_photos))

        for photo in all_photos:
            progress.advance(task)

            # Skip videos
            if photo.ismovie:
                continue

            # Date filter (if not using a specific album)
            photo_date: Optional[datetime] = photo.date
            if not settings.photos_album_name:
                if photo_date is None:
                    continue
                try:
                    _pd = photo_date.replace(tzinfo=None) if photo_date.tzinfo else photo_date
                    _bs = batch_start.replace(tzinfo=None) if batch_start.tzinfo else batch_start
                    _be = batch_end.replace(tzinfo=None) if batch_end.tzinfo else batch_end
                    if not (_bs <= _pd <= _be):
                        continue
                except Exception as exc:
                    logger.debug("Date comparison error for %s: %s", photo.uuid, exc)
                    continue

            # Idempotency check
            if photo.uuid in existing_ids:
                continue

            # GPS
            lat, lon = None, None
            try:
                loc = photo.location
                if loc is not None:
                    lat, lon = loc
            except Exception:
                pass

            yield {
                "id": photo.uuid,
                "original_filename": photo.original_filename,
                "path": photo.path,
                "date": photo_date or datetime.now(),
                "lat": lat,
                "lon": lon,
                "_is_local_file": False,
                "_photo_obj": photo,
            }


async def run_ingestion(
    batch_start: datetime,
    batch_end: datetime,
    job_id: str,
    status_dict: Dict[str, Any],
) -> None:
    """Full ingestion pipeline: scan → privacy filter → extract → export → DB write."""
    status_dict[job_id] = {
        "status": "running",
        "total_scanned": 0,
        "passed_filter": 0,
        "failed_filter": 0,
        "exported": 0,
        "batch_start": batch_start.isoformat(),
        "batch_end": batch_end.isoformat(),
    }

    loop = asyncio.get_event_loop()
    export_dir = Path(settings.export_dir).expanduser()
    export_dir.mkdir(parents=True, exist_ok=True)

    try:
        async for photo_info in scan_library(batch_start, batch_end):
            status_dict[job_id]["total_scanned"] += 1
            image_path: Optional[str] = photo_info["path"]
            is_local = photo_info.get("_is_local_file", False)

            # ------------------------------------------------------------------
            # Privacy filter (Apple Vision on-device)
            # ------------------------------------------------------------------
            if image_path and Path(image_path).exists():
                passed, reason = await loop.run_in_executor(
                    None, privacy_filter.is_landscape_photo, image_path
                )
            else:
                passed, reason = True, "landscape"

            if not passed:
                logger.debug(
                    "Skipping %s: privacy_filter returned (%s, %s)",
                    photo_info["id"],
                    passed,
                    reason,
                )
                status_dict[job_id]["failed_filter"] += 1
                continue

            status_dict[job_id]["passed_filter"] += 1

            # ------------------------------------------------------------------
            # Export / Convert as JPEG
            # ------------------------------------------------------------------
            jpeg_path = export_dir / f"{photo_info['id']}.jpg"

            if is_local:
                # Convert raw local file to sRGB JPEG in export_dir
                from PIL import Image

                def _convert_local(src: str, dst: Path) -> Path:
                    with Image.open(src) as img:
                        rgb = img.convert("RGB")
                        rgb.save(str(dst), format="JPEG", quality=settings.jpeg_quality)
                    return dst

                try:
                    await loop.run_in_executor(None, _convert_local, image_path, jpeg_path)
                except Exception as exc:
                    logger.error("Local file convert failed for %s: %s", image_path, exc)
                    continue
            else:
                photo = photo_info["_photo_obj"]
                try:
                    jpeg_path = await loop.run_in_executor(
                        None,
                        converter.export_as_jpeg,
                        photo,
                        export_dir,
                    )
                except Exception as exc:
                    logger.error("Export failed for %s: %s", photo_info["id"], exc)
                    continue

            # ------------------------------------------------------------------
            # Extract metadata
            # ------------------------------------------------------------------
            try:
                from PIL import Image

                pil_img = await loop.run_in_executor(None, Image.open, str(jpeg_path))
                pil_img.load()
                meta = await loop.run_in_executor(
                    None, exif_extractor.extract_metadata, photo_info.get("_photo_obj"), pil_img
                )
            except Exception:
                meta = {
                    "taken_at": photo_info["date"],
                    "lat": photo_info["lat"],
                    "lon": photo_info["lon"],
                    "sharpness": 100.0,
                    "aspect_ratio": "4:5",
                    "is_landscape": True,
                }

            # ------------------------------------------------------------------
            # Write to SQLite
            # ------------------------------------------------------------------
            try:
                async with get_db() as conn:
                    await conn.execute(
                        """
                        INSERT OR IGNORE INTO photos
                            (id, filepath, taken_at, lat, lon,
                             sharpness, aspect_ratio, is_landscape, export_path)
                        VALUES
                            (:id, :filepath, :taken_at, :lat, :lon,
                             :sharpness, :aspect_ratio, :is_landscape, :export_path)
                        """,
                        {
                            "id": photo_info["id"],
                            "filepath": str(jpeg_path),
                            "taken_at": (
                                meta["taken_at"].isoformat()
                                if meta.get("taken_at")
                                else (photo_info["date"].isoformat() if photo_info.get("date") else None)
                            ),
                            "lat": meta.get("lat"),
                            "lon": meta.get("lon"),
                            "sharpness": meta.get("sharpness"),
                            "aspect_ratio": meta.get("aspect_ratio"),
                            "is_landscape": 1,
                            "export_path": str(jpeg_path),
                        },
                    )
                    await conn.commit()
                status_dict[job_id]["exported"] += 1
            except Exception as exc:
                logger.error("DB write failed for %s: %s", photo_info["id"], exc)

    except Exception as exc:
        logger.exception("Ingestion job %s failed: %s", job_id, exc)
        status_dict[job_id]["status"] = "error"
        status_dict[job_id]["error"] = str(exc)
        return

    status_dict[job_id]["status"] = "done"
    logger.info(
        "Ingestion job %s complete: scanned=%d passed=%d exported=%d",
        job_id,
        status_dict[job_id]["total_scanned"],
        status_dict[job_id]["passed_filter"],
        status_dict[job_id]["exported"],
    )
