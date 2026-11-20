"""Pydantic response/request models shared across all Horizn API routes."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Photo
# ---------------------------------------------------------------------------


class PhotoRecord(BaseModel):
    """Mirrors the `photos` database table."""

    id: str
    filepath: str
    taken_at: Optional[datetime] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    sharpness: Optional[float] = None
    aspect_ratio: Optional[str] = None
    is_landscape: bool = False
    export_path: Optional[str] = None
    ingested_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Carousel
# ---------------------------------------------------------------------------


class CarouselSlide(BaseModel):
    """A single slide within a carousel draft."""

    position: int = Field(..., ge=0, description="Zero-based display order.")
    photo_id: str
    export_path: Optional[str] = None
    caption: Optional[str] = None


class CarouselDraft(BaseModel):
    """A carousel in any lifecycle state (draft → ready → published)."""

    id: str
    status: str = "draft"
    aspect_ratio: Optional[str] = None
    caption: Optional[str] = None
    hashtags: List[str] = Field(default_factory=list)
    slides: List[CarouselSlide] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------


class IngestStatus(BaseModel):
    """Summary returned after an ingestion run."""

    total_scanned: int = 0
    passed_filter: int = 0
    failed_filter: int = 0
    exported: int = 0
    batch_start: Optional[datetime] = None
    batch_end: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Publishing
# ---------------------------------------------------------------------------


class PublishStatus(BaseModel):
    """A single publish-log event entry."""

    carousel_id: str
    event: str
    detail: Optional[str] = None
