"""FastAPI router for carousel curation, preview, reordering, and slide management."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from horizn.api.models import CarouselDraft, CarouselSlide
from horizn.config import settings
from horizn.curation import aspect_ratio, caption_gen, clusterer, deduplicator, sequencer
from horizn.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory curation job status store
_curation_jobs: Dict[str, Dict[str, Any]] = {}
_curation_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Curation Orchestration
# ---------------------------------------------------------------------------


async def run_curation(job_id: str) -> None:
    """Full curation pipeline:
    1. Clear any prior un-published drafts so clean, deterministic carousels are generated.
    2. Reset duplicate_of for un-published photos.
    3. Globally deduplicate photos via multi-hash (pHash + dHash) and burst proximity.
    4. Cluster Hero Shots by GPS proximity and visual subjects.
    5. For each cluster:
       - Double-check burst deduplication.
       - Align aspect ratio to majority with letterboxing.
       - Sequence slides via Gemini 2.5 Flash (Hook -> Body -> Closer).
       - Generate caption & hashtags via Gemini 2.5 Pro.
       - Save to carousels & carousel_slides tables.
    """
    async with _curation_lock:
        _curation_jobs[job_id]["status"] = "running"
        logger.info("Starting curation job %s...", job_id)

        try:
            # 1. Clean up any un-published drafts to guarantee no duplicate drafts or overlapping runs
            async with get_db() as conn:
                await conn.execute("DELETE FROM carousel_slides WHERE carousel_id IN (SELECT id FROM carousels WHERE status = 'draft')")
                await conn.execute("DELETE FROM publish_log WHERE carousel_id IN (SELECT id FROM carousels WHERE status = 'draft')")
                await conn.execute("DELETE FROM carousels WHERE status = 'draft'")
                await conn.execute(
                    """
                    UPDATE photos SET duplicate_of = NULL 
                    WHERE id NOT IN (SELECT photo_id FROM carousel_slides)
                    """
                )
                await conn.commit()

                # Fetch eligible photos: landscape scenery photos that are uncurated
                async with conn.execute(
                    """
                    SELECT p.* FROM photos p
                    LEFT JOIN carousel_slides cs ON p.id = cs.photo_id
                    WHERE p.is_landscape = 1 
                      AND cs.photo_id IS NULL 
                      AND p.export_path IS NOT NULL
                    ORDER BY p.taken_at ASC
                    """
                ) as cursor:
                    rows = await cursor.fetchall()
                    photos = [dict(r) for r in rows]

            _curation_jobs[job_id]["photos_found"] = len(photos)
            logger.info("Found %d uncurated candidate scenery photos.", len(photos))

            if not photos:
                _curation_jobs[job_id]["status"] = "completed"
                _curation_jobs[job_id]["carousels_created"] = 0
                return

            # 2. Global deduplication: group near-identical / burst photos across the session,
            # pick the single sharpest 'Hero Shot' per scene, and map duplicate siblings.
            heroes, duplicate_map = deduplicator.deduplicate_candidates(photos)
            logger.info(
                "Global deduplication: %d candidate photos reduced to %d hero shots (%d duplicates identified).",
                len(photos),
                len(heroes),
                sum(len(dups) for dups in duplicate_map.values()),
            )

            # Record duplicate relationships in DB
            if duplicate_map:
                async with get_db() as conn:
                    for hero_id, dup_ids in duplicate_map.items():
                        for dup_id in dup_ids:
                            await conn.execute(
                                "UPDATE photos SET duplicate_of = ? WHERE id = ?",
                                (hero_id, dup_id),
                            )
                    await conn.commit()

            # 3. Cluster hero photos with visual subject intelligence
            clusters = await clusterer.cluster_photos(heroes)
            logger.info("Formed %d clusters from %d hero photos.", len(clusters), len(heroes))
            _curation_jobs[job_id]["total_clusters"] = len(clusters)

            carousels_created = 0

            for idx, raw_group in enumerate(clusters):
                _curation_jobs[job_id]["current_cluster"] = idx + 1
                if not raw_group:
                    continue

                # 4. Intra-cluster burst deduplication safety net
                deduped = deduplicator.deduplicate_cluster(raw_group)
                if not deduped:
                    continue

                # 5. Align aspect ratio
                aligned = aspect_ratio.align_aspect_ratios(deduped, settings.export_dir)

                # 6. Sequence slides (Gemini Flash)
                if len(aligned) > 1:
                    sequenced = await sequencer.sequence_slides(aligned)
                else:
                    sequenced = aligned

                # 7. Generate caption & hashtags (Gemini Pro)
                loc_hint = None
                if sequenced[0].get("lat") and sequenced[0].get("lon"):
                    loc_hint = f"Coordinates: {sequenced[0]['lat']:.3f}, {sequenced[0]['lon']:.3f}"

                caption, hashtags = await caption_gen.generate_caption(sequenced, location_hint=loc_hint)

                # Determine dominant aspect ratio
                maj_ratio = sequenced[0].get("aspect_ratio") or "4:5"

                # 8. Save to database
                c_id = str(uuid4())
                async with get_db() as conn:
                    await conn.execute(
                        """
                        INSERT INTO carousels (id, status, aspect_ratio, caption, hashtags)
                        VALUES (?, 'draft', ?, ?, ?)
                        """,
                        (c_id, maj_ratio, caption, json.dumps(hashtags)),
                    )

                    for pos, slide_photo in enumerate(sequenced):
                        await conn.execute(
                            """
                            INSERT INTO carousel_slides (carousel_id, photo_id, position, caption)
                            VALUES (?, ?, ?, NULL)
                            """,
                            (c_id, slide_photo["id"], pos),
                        )

                    await conn.commit()

                carousels_created += 1
                _curation_jobs[job_id]["carousels_created"] = carousels_created

                # Pacing delay between carousels to stay safely within Gemini Free Tier (15 RPM)
                await asyncio.sleep(4.0)

            _curation_jobs[job_id]["status"] = "completed"
            logger.info("Curation job %s completed. Created %d carousels.", job_id, carousels_created)

        except Exception as exc:
            logger.exception("Curation job %s failed: %s", job_id, exc)
            _curation_jobs[job_id]["status"] = "failed"
            _curation_jobs[job_id]["error"] = str(exc)


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------


class CurationRunResponse(BaseModel):
    job_id: str
    status: str


class UpdateCarouselRequest(BaseModel):
    caption: Optional[str] = None
    hashtags: Optional[List[str]] = None
    status: Optional[str] = None
    slide_order: Optional[List[str]] = Field(
        None, description="Ordered list of photo_id strings to reorder slides"
    )


class ManualCarouselRequest(BaseModel):
    photo_ids: List[str]


@router.post("/manual", response_model=CarouselDraft)
@router.post("/curate/manual", response_model=CarouselDraft)
async def create_manual_carousel(body: ManualCarouselRequest) -> CarouselDraft:
    """Create a new carousel draft from manually selected photos, with Gemini AI sequencing and captioning."""
    if not body.photo_ids:
        raise HTTPException(status_code=400, detail="At least 1 photo must be selected.")
    if len(body.photo_ids) > 10:
        raise HTTPException(status_code=400, detail="Instagram carousels support a maximum of 10 slides.")

    # 1. Fetch the photos from DB
    async with get_db() as conn:
        placeholders = ",".join(["?"] * len(body.photo_ids))
        async with conn.execute(
            f"SELECT * FROM photos WHERE id IN ({placeholders})", body.photo_ids
        ) as cursor:
            rows = await cursor.fetchall()
            raw_photos = [dict(r) for r in rows]

    if not raw_photos:
        raise HTTPException(status_code=404, detail="Selected photos not found in library.")

    # Maintain selected order
    id_to_photo = {p["id"]: p for p in raw_photos}
    selected_photos = [id_to_photo[pid] for pid in body.photo_ids if pid in id_to_photo]

    # 2. Align aspect ratios
    aligned = aspect_ratio.align_aspect_ratios(selected_photos, settings.export_dir)

    # 3. Sequence slides (Gemini Flash narrative order)
    if len(aligned) > 1:
        sequenced = await sequencer.sequence_slides(aligned)
    else:
        sequenced = aligned

    # Pause briefly to prevent rate limit bursting between sequencing and captioning
    await asyncio.sleep(0.5)

    # 4. Generate caption & hashtags
    loc_hint = None
    if sequenced[0].get("lat") and sequenced[0].get("lon"):
        loc_hint = f"Coordinates: {sequenced[0]['lat']:.3f}, {sequenced[0]['lon']:.3f}"

    caption, hashtags = await caption_gen.generate_caption(sequenced, location_hint=loc_hint)

    # 5. Determine dominant aspect ratio
    maj_ratio = sequenced[0].get("aspect_ratio") or "4:5"

    # 6. Save new draft to DB
    c_id = str(uuid4())
    async with get_db() as conn:
        await conn.execute(
            """
            INSERT INTO carousels (id, status, aspect_ratio, caption, hashtags)
            VALUES (?, 'draft', ?, ?, ?)
            """,
            (c_id, maj_ratio, caption, json.dumps(hashtags)),
        )

        for pos, slide_photo in enumerate(sequenced):
            await conn.execute(
                """
                INSERT INTO carousel_slides (carousel_id, photo_id, position, caption)
                VALUES (?, ?, ?, NULL)
                """,
                (c_id, slide_photo["id"], pos),
            )

        await conn.commit()

    return await get_carousel(c_id)


@router.post("/curate/run", response_model=CurationRunResponse)
async def trigger_curation(background_tasks: BackgroundTasks) -> CurationRunResponse:
    """Trigger the automated carousel clustering, sequencing, and caption generation."""
    if _curation_lock.locked():
        raise HTTPException(
            status_code=409,
            detail="A curation job is already in progress. Please wait for it to complete.",
        )
    job_id = str(uuid4())
    _curation_jobs[job_id] = {
        "job_id": job_id,
        "status": "started",
        "photos_found": 0,
        "carousels_created": 0,
    }
    background_tasks.add_task(run_curation, job_id)
    return CurationRunResponse(job_id=job_id, status="started")


@router.get("/curate/status/{job_id}")
async def get_curation_status(job_id: str) -> dict:
    """Check the status of a running curation job."""
    if job_id not in _curation_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return _curation_jobs[job_id]


@router.get("", response_model=List[CarouselDraft])
@router.get("/", response_model=List[CarouselDraft])
async def list_carousels(status: Optional[str] = Query(None)) -> List[CarouselDraft]:
    """List all carousels, optionally filtered by status (e.g. 'draft', 'published')."""
    async with get_db() as conn:
        query = "SELECT * FROM carousels"
        params: list[Any] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC"

        async with conn.execute(query, params) as cursor:
            c_rows = await cursor.fetchall()

        drafts: list[CarouselDraft] = []
        for c in c_rows:
            # Fetch slides with photos
            async with conn.execute(
                """
                SELECT cs.position, cs.photo_id, cs.caption as slide_caption, p.export_path
                FROM carousel_slides cs
                JOIN photos p ON cs.photo_id = p.id
                WHERE cs.carousel_id = ?
                ORDER BY cs.position ASC
                """,
                (c["id"],),
            ) as s_cursor:
                slide_rows = await s_cursor.fetchall()

            slides = [
                CarouselSlide(
                    position=s["position"],
                    photo_id=s["photo_id"],
                    export_path=s["export_path"],
                    caption=s["slide_caption"],
                )
                for s in slide_rows
            ]

            tags = []
            if c["hashtags"]:
                try:
                    tags = json.loads(c["hashtags"])
                except Exception:
                    tags = []

            drafts.append(
                CarouselDraft(
                    id=c["id"],
                    status=c["status"],
                    aspect_ratio=c["aspect_ratio"],
                    caption=c["caption"],
                    hashtags=tags,
                    slides=slides,
                )
            )

        return drafts


@router.get("/{carousel_id}", response_model=CarouselDraft)
async def get_carousel(carousel_id: str) -> CarouselDraft:
    """Get single carousel draft by ID with its slides."""
    async with get_db() as conn:
        async with conn.execute("SELECT * FROM carousels WHERE id = ?", (carousel_id,)) as cursor:
            c = await cursor.fetchone()
            if not c:
                raise HTTPException(status_code=404, detail="Carousel not found")

        async with conn.execute(
            """
            SELECT cs.position, cs.photo_id, cs.caption as slide_caption, p.export_path
            FROM carousel_slides cs
            JOIN photos p ON cs.photo_id = p.id
            WHERE cs.carousel_id = ?
            ORDER BY cs.position ASC
            """,
            (carousel_id,),
        ) as s_cursor:
            slide_rows = await s_cursor.fetchall()

        slides = [
            CarouselSlide(
                position=s["position"],
                photo_id=s["photo_id"],
                export_path=s["export_path"],
                caption=s["slide_caption"],
            )
            for s in slide_rows
        ]

        tags = []
        if c["hashtags"]:
            try:
                tags = json.loads(c["hashtags"])
            except Exception:
                tags = []

        return CarouselDraft(
            id=c["id"],
            status=c["status"],
            aspect_ratio=c["aspect_ratio"],
            caption=c["caption"],
            hashtags=tags,
            slides=slides,
        )


@router.put("/{carousel_id}", response_model=CarouselDraft)
async def update_carousel(carousel_id: str, body: UpdateCarouselRequest) -> CarouselDraft:
    """Update caption, hashtags, status, or slide order of a carousel draft."""
    async with get_db() as conn:
        # Check exists
        async with conn.execute("SELECT id FROM carousels WHERE id = ?", (carousel_id,)) as cursor:
            if not await cursor.fetchone():
                raise HTTPException(status_code=404, detail="Carousel not found")

        # Update carousel fields
        updates = []
        params = []
        if body.caption is not None:
            updates.append("caption = ?")
            params.append(body.caption)
        if body.hashtags is not None:
            updates.append("hashtags = ?")
            params.append(json.dumps(body.hashtags))
        if body.status is not None:
            updates.append("status = ?")
            params.append(body.status)

        if updates:
            params.append(carousel_id)
            await conn.execute(
                f"UPDATE carousels SET {', '.join(updates)} WHERE id = ?", params
            )

        # Reorder slides if provided
        if body.slide_order:
            for new_pos, photo_id in enumerate(body.slide_order):
                await conn.execute(
                    """
                    UPDATE carousel_slides
                    SET position = ?
                    WHERE carousel_id = ? AND photo_id = ?
                    """,
                    (new_pos, carousel_id, photo_id),
                )

        await conn.commit()

    return await get_carousel(carousel_id)


@router.delete("/{carousel_id}/slides/{photo_id}", response_model=CarouselDraft)
async def remove_slide(
    carousel_id: str,
    photo_id: str,
    delete_from_library: bool = False,
) -> CarouselDraft:
    """Remove a slide from a carousel and re-index the remaining slide positions.
    Optionally delete the photo from the library altogether."""
    async with get_db() as conn:
        await conn.execute(
            "DELETE FROM carousel_slides WHERE carousel_id = ? AND photo_id = ?",
            (carousel_id, photo_id),
        )

        if delete_from_library:
            await conn.execute("UPDATE photos SET duplicate_of = NULL WHERE duplicate_of = ?", (photo_id,))
            await conn.execute("DELETE FROM photos WHERE id = ?", (photo_id,))

        # Re-index remaining positions
        async with conn.execute(
            "SELECT photo_id FROM carousel_slides WHERE carousel_id = ? ORDER BY position ASC",
            (carousel_id,),
        ) as cursor:
            remaining = await cursor.fetchall()

        if not remaining:
            # If all slides removed, delete draft carousel
            await conn.execute("DELETE FROM publish_log WHERE carousel_id = ?", (carousel_id,))
            await conn.execute("DELETE FROM carousels WHERE id = ?", (carousel_id,))
            await conn.commit()
            return CarouselDraft(
                id=carousel_id,
                status="deleted",
                aspect_ratio="4:5",
                caption="",
                hashtags=[],
                slides=[],
            )

        for idx, row in enumerate(remaining):
            await conn.execute(
                "UPDATE carousel_slides SET position = ? WHERE carousel_id = ? AND photo_id = ?",
                (idx, carousel_id, row["photo_id"]),
            )

        await conn.commit()

    return await get_carousel(carousel_id)


@router.delete("/drafts/all")
async def clear_all_drafts(delete_from_library: bool = False) -> dict:
    """Delete all carousels that are currently in 'draft' status.
    Optionally delete their underlying photos from the library and disk."""
    async with get_db() as conn:
        async with conn.execute("SELECT id FROM carousels WHERE status = 'draft'") as cursor:
            draft_ids = [row["id"] for row in await cursor.fetchall()]

        if not draft_ids:
            return {"status": "cleared", "deleted_count": 0}

        photo_ids_to_delete: set[str] = set()

        for d_id in draft_ids:
            if delete_from_library:
                async with conn.execute(
                    "SELECT photo_id FROM carousel_slides WHERE carousel_id = ?", (d_id,)
                ) as p_cur:
                    p_rows = await p_cur.fetchall()
                    for pr in p_rows:
                        photo_ids_to_delete.add(pr["photo_id"])

            # Delete child references first to satisfy foreign key constraints
            await conn.execute("DELETE FROM carousel_slides WHERE carousel_id = ?", (d_id,))
            await conn.execute("DELETE FROM publish_log WHERE carousel_id = ?", (d_id,))
            await conn.execute("DELETE FROM carousels WHERE id = ?", (d_id,))

        # Delete underlying photos after carousel_slides references have been removed
        if delete_from_library and photo_ids_to_delete:
            for p_id in photo_ids_to_delete:
                await conn.execute("UPDATE photos SET duplicate_of = NULL WHERE duplicate_of = ?", (p_id,))
                async with conn.execute("SELECT export_path FROM photos WHERE id = ?", (p_id,)) as exp_cur:
                    exp_row = await exp_cur.fetchone()
                    if exp_row and exp_row["export_path"]:
                        try:
                            p = Path(exp_row["export_path"])
                            if p.exists():
                                p.unlink(missing_ok=True)
                            ig_p = p.parent / f"{p.stem}_ig.jpg"
                            if ig_p.exists():
                                ig_p.unlink(missing_ok=True)
                        except Exception:
                            pass
                await conn.execute("DELETE FROM photos WHERE id = ?", (p_id,))
        elif not delete_from_library:
            # If drafts were cleared without deleting photos from library, release duplicate_of
            # for photos whose hero was in that cleared draft, so they can be re-curated cleanly.
            await conn.execute(
                """
                UPDATE photos SET duplicate_of = NULL 
                WHERE id NOT IN (SELECT photo_id FROM carousel_slides)
                  AND (duplicate_of IS NULL OR duplicate_of NOT IN (SELECT photo_id FROM carousel_slides))
                """
            )

        await conn.commit()

    return {"status": "cleared", "deleted_count": len(draft_ids)}


@router.delete("/{carousel_id}")
async def delete_carousel(carousel_id: str) -> dict:
    """Delete a single carousel draft."""
    async with get_db() as conn:
        await conn.execute("DELETE FROM carousel_slides WHERE carousel_id = ?", (carousel_id,))
        await conn.execute("DELETE FROM publish_log WHERE carousel_id = ?", (carousel_id,))
        await conn.execute("DELETE FROM carousels WHERE id = ?", (carousel_id,))

        # Release duplicate_of for photos whose hero was in this deleted draft and not in another carousel
        await conn.execute(
            """
            UPDATE photos SET duplicate_of = NULL 
            WHERE id NOT IN (SELECT photo_id FROM carousel_slides)
              AND duplicate_of IS NOT NULL
              AND duplicate_of NOT IN (SELECT photo_id FROM carousel_slides)
            """
        )
        await conn.commit()

    return {"status": "deleted", "id": carousel_id}


class AICaptionRequest(BaseModel):
    instruction: Optional[str] = Field(default=None, description="Optional user prompt or creative guidance")
    mode: str = Field(default="refine", description="'refine' to modify existing caption, or 'scratch' to generate fresh")
    current_caption: Optional[str] = Field(default=None, description="Current caption in the editor")


class AICaptionResponse(BaseModel):
    caption: str
    hashtags: List[str]


@router.post("/{carousel_id}/ai-caption", response_model=AICaptionResponse)
async def generate_ai_caption(carousel_id: str, body: AICaptionRequest) -> AICaptionResponse:
    """Generate or refine caption and hashtags for a carousel using Gemini AI."""
    async with get_db() as conn:
        async with conn.execute(
            "SELECT id, caption, hashtags FROM carousels WHERE id = ?", (carousel_id,)
        ) as cursor:
            carousel_row = await cursor.fetchone()
            if not carousel_row:
                raise HTTPException(status_code=404, detail="Carousel not found")

        async with conn.execute(
            """
            SELECT cs.position, cs.photo_id, p.export_path, p.lat, p.lon, p.taken_at
            FROM carousel_slides cs
            JOIN photos p ON cs.photo_id = p.id
            WHERE cs.carousel_id = ?
            ORDER BY cs.position ASC
            """,
            (carousel_id,),
        ) as cursor:
            slide_rows = await cursor.fetchall()
            photos = [dict(r) for r in slide_rows]

    location_hint = None
    for p in photos:
        if p.get("lat") and p.get("lon"):
            location_hint = f"GPS: {p['lat']:.4f}, {p['lon']:.4f}"
            break

    curr_cap = body.current_caption if body.current_caption is not None else carousel_row["caption"]

    caption, hashtags = await caption_gen.refine_or_generate_caption(
        photos=photos,
        current_caption=curr_cap,
        instruction=body.instruction,
        location_hint=location_hint,
        mode=body.mode,
    )

    return AICaptionResponse(caption=caption, hashtags=hashtags)
