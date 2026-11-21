"""FastAPI router for photo ingestion endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from horizn.config import settings
from horizn.ingestion.reader import run_ingestion

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# In-memory job status store (keyed by job_id string)
# ---------------------------------------------------------------------------
# Maps job_id -> dict with keys: status, total_scanned, passed_filter,
# failed_filter, exported, batch_start, batch_end, [error]
_status_store: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class IngestRunRequest(BaseModel):
    batch_start: Optional[str] = None  # ISO 8601 date/datetime string
    batch_end: Optional[str] = None  # ISO 8601 date/datetime string


class IngestRunResponse(BaseModel):
    job_id: str
    status: str


# ---------------------------------------------------------------------------
# POST /ingest/run
# ---------------------------------------------------------------------------


@router.post("/run", response_model=IngestRunResponse)
async def start_ingestion(
    body: IngestRunRequest,
    background_tasks: BackgroundTasks,
) -> IngestRunResponse:
    """Launch an ingestion job in the background.

    Accepts optional ISO 8601 date strings for *batch_start* and *batch_end*.
    If omitted, falls back to settings.ingest_start_date/ingest_end_date or
    settings.ingest_batch_months (relative to now, 0 = all time).
    Returns a *job_id* that can be used to poll SSE status.
    """
    now = datetime.now()

    # Determine start date
    if body.batch_start:
        try:
            batch_start = datetime.fromisoformat(body.batch_start)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid batch_start: {exc}") from exc
    elif settings.ingest_start_date:
        try:
            batch_start = datetime.fromisoformat(settings.ingest_start_date)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid INGEST_START_DATE in settings: {exc}") from exc
    elif settings.ingest_batch_months > 0:
        days = int(settings.ingest_batch_months * 30.4375)
        batch_start = now - timedelta(days=days)
    else:
        # All-time scan (from beginning of epoch)
        batch_start = datetime(1970, 1, 1)

    # Determine end date
    if body.batch_end:
        try:
            batch_end = datetime.fromisoformat(body.batch_end)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid batch_end: {exc}") from exc
    elif settings.ingest_end_date:
        try:
            batch_end = datetime.fromisoformat(settings.ingest_end_date)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid INGEST_END_DATE in settings: {exc}") from exc
    else:
        batch_end = now

    if batch_start > batch_end:
        raise HTTPException(
            status_code=422,
            detail="batch_start must be before batch_end",
        )

    job_id = str(uuid4())
    _status_store[job_id] = {"status": "queued"}

    background_tasks.add_task(
        run_ingestion,
        batch_start,
        batch_end,
        job_id,
        _status_store,
    )

    logger.info("Ingestion job %s queued for %s → %s", job_id, batch_start, batch_end)
    return IngestRunResponse(job_id=job_id, status="started")


# ---------------------------------------------------------------------------
# GET /ingest/status/{job_id}  –  SSE stream
# ---------------------------------------------------------------------------


async def _status_event_generator(job_id: str):
    """Async generator that yields SSE-formatted lines every second.

    Yields until the job status is "done" or "error".
    If the job_id is unknown, yields a single error event and stops.
    """
    if job_id not in _status_store:
        payload = json.dumps({"error": "unknown job_id", "job_id": job_id})
        yield f"data: {payload}\n\n"
        return

    while True:
        status = _status_store.get(job_id, {})
        payload = json.dumps(status)
        yield f"data: {payload}\n\n"

        current = status.get("status", "queued")
        if current in ("done", "error"):
            break

        await asyncio.sleep(1)


@router.get("/status/{job_id}")
async def ingest_status(job_id: str) -> StreamingResponse:
    """Stream ingestion job status as Server-Sent Events (SSE).

    Returns a ``text/event-stream`` response that emits a JSON-encoded
    :class:`~horizn.api.models.IngestStatus`-compatible object every second
    until the job reaches a terminal state (*done* or *error*).
    """
    return StreamingResponse(
        _status_event_generator(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# GET /ingest/stats
# ---------------------------------------------------------------------------


@router.get("/stats")
async def get_ingest_stats() -> dict:
    """Return live counts of total synced photos, uncurated photos, and draft carousels."""
    from horizn.database import get_db

    async with get_db() as conn:
        async with conn.execute("SELECT COUNT(*) as total FROM photos") as cur:
            row = await cur.fetchone()
            total_photos = row["total"] if row else 0

        async with conn.execute(
            """
            SELECT COUNT(*) as uncurated FROM photos p
            LEFT JOIN carousel_slides cs ON p.id = cs.photo_id
            WHERE p.is_landscape = 1 
              AND cs.photo_id IS NULL 
              AND p.export_path IS NOT NULL
              AND p.duplicate_of IS NULL
            """
        ) as cur:
            row = await cur.fetchone()
            uncurated_photos = row["uncurated"] if row else 0

        async with conn.execute(
            """
            SELECT COUNT(*) as alternates FROM photos p
            WHERE p.duplicate_of IS NOT NULL
            """
        ) as cur:
            row = await cur.fetchone()
            alternate_photos = row["alternates"] if row else 0

        async with conn.execute("SELECT COUNT(*) as total FROM carousels WHERE status = 'draft'") as cur:
            row = await cur.fetchone()
            draft_carousels = row["total"] if row else 0

    return {
        "total_photos": total_photos,
        "uncurated_photos": uncurated_photos,
        "alternate_photos": alternate_photos,
        "draft_carousels": draft_carousels,
    }
