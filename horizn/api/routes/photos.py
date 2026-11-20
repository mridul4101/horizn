"""FastAPI router for photo library management endpoints."""

from __future__ import annotations

import logging
from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from horizn.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


class PhotoItem(BaseModel):
    id: str
    filepath: str
    export_path: Optional[str] = None
    taken_at: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    sharpness: Optional[float] = None
    aspect_ratio: Optional[str] = None
    is_landscape: int = 1
    ingested_at: Optional[str] = None
    carousel_id: Optional[str] = None
    status: str = "awaiting_curation"  # awaiting_curation | in_carousel | excluded


class BatchDeleteRequest(BaseModel):
    photo_ids: List[str]


@router.get("", response_model=List[PhotoItem])
@router.get("/", response_model=List[PhotoItem])
async def list_photos() -> List[PhotoItem]:
    """Return all photos in the local library with carousel assignment status."""
    async with get_db() as conn:
        async with conn.execute(
            """
            SELECT 
                p.id, p.filepath, p.export_path, p.taken_at, p.lat, p.lon, 
                p.sharpness, p.aspect_ratio, p.is_landscape, p.ingested_at,
                cs.carousel_id
            FROM photos p
            LEFT JOIN carousel_slides cs ON p.id = cs.photo_id
            ORDER BY p.taken_at DESC, p.ingested_at DESC
            """
        ) as cursor:
            rows = await cursor.fetchall()

    results: List[PhotoItem] = []
    for r in rows:
        row_dict = dict(r)
        c_id = row_dict.get("carousel_id")
        if c_id:
            status = "in_carousel"
        elif row_dict.get("is_landscape") == 1:
            status = "awaiting_curation"
        else:
            status = "excluded"

        results.append(
            PhotoItem(
                id=row_dict["id"],
                filepath=row_dict["filepath"],
                export_path=row_dict.get("export_path"),
                taken_at=str(row_dict["taken_at"]) if row_dict.get("taken_at") else None,
                lat=row_dict.get("lat"),
                lon=row_dict.get("lon"),
                sharpness=row_dict.get("sharpness"),
                aspect_ratio=row_dict.get("aspect_ratio"),
                is_landscape=row_dict.get("is_landscape") or 1,
                ingested_at=str(row_dict["ingested_at"]) if row_dict.get("ingested_at") else None,
                carousel_id=c_id,
                status=status,
            )
        )
    return results


@router.delete("/{photo_id}")
async def delete_photo(photo_id: str) -> dict:
    """Delete a single photo from both carousel slides and the photo library."""
    async with get_db() as conn:
        await conn.execute("DELETE FROM carousel_slides WHERE photo_id = ?", (photo_id,))
        await conn.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
        await conn.commit()
    return {"status": "deleted", "id": photo_id}


@router.post("/batch-delete")
async def batch_delete_photos(body: BatchDeleteRequest) -> dict:
    """Delete multiple photos from the library and any carousels containing them."""
    if not body.photo_ids:
        return {"status": "noop", "deleted_count": 0}

    async with get_db() as conn:
        for p_id in body.photo_ids:
            await conn.execute("DELETE FROM carousel_slides WHERE photo_id = ?", (p_id,))
            await conn.execute("DELETE FROM photos WHERE id = ?", (p_id,))
        await conn.commit()

    return {"status": "deleted", "deleted_count": len(body.photo_ids)}
