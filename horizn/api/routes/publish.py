"""FastAPI router for publishing carousels to Instagram."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from horizn.database import get_db
from horizn.publisher.instagram import publish_carousel

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory tracking of publish task status
_publish_jobs: Dict[str, Dict[str, Any]] = {}


class PublishResponse(BaseModel):
    job_id: str
    carousel_id: str
    status: str
    ig_media_id: Optional[str] = None
    start_log_id: int = 0


async def _run_publish_task(job_id: str, carousel_id: str) -> None:
    _publish_jobs[job_id] = {
        "job_id": job_id,
        "carousel_id": carousel_id,
        "status": "running",
        "events": [],
    }

    async def callback(event: str, detail: str) -> None:
        _publish_jobs[job_id]["events"].append({"event": event, "detail": detail})

    try:
        ig_media_id = await publish_carousel(carousel_id, status_callback=callback)
        _publish_jobs[job_id]["status"] = "completed"
        _publish_jobs[job_id]["ig_media_id"] = ig_media_id
    except Exception as exc:
        logger.exception("Publish failed for carousel %s: %s", carousel_id, exc)
        _publish_jobs[job_id]["status"] = "failed"
        _publish_jobs[job_id]["error"] = str(exc)

        # Record error in DB so SSE stream and UI immediately receive the failure
        try:
            async with get_db() as conn:
                await conn.execute("UPDATE carousels SET status = 'failed' WHERE id = ?", (carousel_id,))
                await conn.execute(
                    "INSERT INTO publish_log (carousel_id, event, detail) VALUES (?, 'error', ?)",
                    (carousel_id, str(exc)),
                )
                await conn.commit()
        except Exception as db_exc:
            logger.warning("Could not record publish error in DB: %s", db_exc)


@router.post("/{carousel_id}", response_model=PublishResponse)
async def trigger_publish(
    carousel_id: str,
    background_tasks: BackgroundTasks,
) -> PublishResponse:
    """Trigger the publish pipeline for an approved carousel draft."""
    # Check if carousel exists or is already published
    async with get_db() as conn:
        async with conn.execute(
            "SELECT id, status, ig_media_id FROM carousels WHERE id = ?", (carousel_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"Carousel {carousel_id} not found")
            if row["status"] == "published":
                return PublishResponse(
                    job_id="already_published",
                    carousel_id=carousel_id,
                    status="already_published",
                    ig_media_id=row["ig_media_id"],
                    start_log_id=0,
                )

        async with conn.execute(
            "SELECT COALESCE(MAX(id), 0) as max_id FROM publish_log WHERE carousel_id = ?",
            (carousel_id,),
        ) as cursor:
            log_row = await cursor.fetchone()
            start_log_id = log_row["max_id"] if log_row else 0

    job_id = str(uuid4())
    _publish_jobs[job_id] = {
        "job_id": job_id,
        "carousel_id": carousel_id,
        "status": "started",
        "events": [],
    }
    background_tasks.add_task(_run_publish_task, job_id, carousel_id)
    return PublishResponse(
        job_id=job_id,
        carousel_id=carousel_id,
        status="started",
        start_log_id=start_log_id,
    )


@router.get("/{carousel_id}/status")
async def publish_status_stream(carousel_id: str, since_id: int = 0) -> StreamingResponse:
    """Stream live publish logs for a carousel using Server-Sent Events (SSE)."""

    async def event_generator() -> AsyncGenerator[str, None]:
        last_log_id = since_id
        terminal_states = {"published", "failed"}

        while True:
            # Query publish_log from DB
            async with get_db() as conn:
                async with conn.execute(
                    """
                    SELECT id, event, detail, ts
                    FROM publish_log
                    WHERE carousel_id = ? AND id > ?
                    ORDER BY id ASC
                    """,
                    (carousel_id, last_log_id),
                ) as cursor:
                    rows = await cursor.fetchall()
                    for r in rows:
                        last_log_id = r["id"]
                        data = json.dumps({
                            "id": r["id"],
                            "event": r["event"],
                            "detail": r["detail"],
                            "ts": r["ts"],
                        })
                        yield f"data: {data}\n\n"

                # Check if carousel reached terminal status
                async with conn.execute(
                    "SELECT status, ig_media_id FROM carousels WHERE id = ?", (carousel_id,)
                ) as cursor:
                    c_row = await cursor.fetchone()
                    if c_row and c_row["status"] in terminal_states:
                        final_data = json.dumps({
                            "event": "done",
                            "status": c_row["status"],
                            "ig_media_id": c_row["ig_media_id"],
                        })
                        yield f"data: {final_data}\n\n"
                        break

            await asyncio.sleep(1.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
