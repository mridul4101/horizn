"""Application settings loaded from the .env file via Pydantic BaseSettings."""

from pathlib import Path
from typing import Any, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Ingestion Source Options
    photos_library_path: Path = Field(
        default=Path("~/Pictures/Photos Library.photoslibrary"),
        description="Absolute (or ~-prefixed) path to the Apple Photos library.",
    )
    photos_album_name: Optional[str] = Field(
        default=None,
        description="Optional Apple Photos album name (e.g. 'Horizn'). If set, only photos in this album are ingested.",
    )
    local_photos_dir: Optional[Path] = Field(
        default=None,
        description="Optional local folder path (e.g. ~/Pictures/MyShots). If set, reads directly from this folder instead of Apple Photos.",
    )
    ingest_batch_months: int = Field(
        default=12,
        description="How many months back to scan during each ingestion run (when not using an album/folder). Set to 0 for all time.",
    )
    ingest_start_date: Optional[str] = Field(
        default=None,
        description="Optional fixed start date (YYYY-MM-DD) for library scans.",
    )
    ingest_end_date: Optional[str] = Field(
        default=None,
        description="Optional fixed end date (YYYY-MM-DD) for library scans.",
    )

    # Privacy Filter
    face_confidence_threshold: float = Field(
        default=0.7,
        description="Vision framework confidence threshold for face detection (0–1).",
    )
    min_face_area_ratio: float = Field(
        default=0.03,
        description="Minimum face bounding-box area ratio to trigger exclusion.",
    )

    # Export
    export_dir: Path = Field(
        default=Path("./data/exports"),
        description="Directory where JPEG exports are written.",
    )
    jpeg_quality: int = Field(
        default=92,
        ge=1,
        le=100,
        description="JPEG compression quality (1–100).",
    )

    # Gemini API
    gemini_api_key: str = Field(default="", description="Google Gemini API key.")
    gemini_flash_model: str = Field(
        default="gemini-3.8-flash",
        description="Gemini model for fast sequencing and visual clustering.",
    )
    gemini_pro_model: str = Field(
        default="gemini-3.8-flash",
        description="Gemini model for evocative captioning.",
    )

    @field_validator("gemini_flash_model", "gemini_pro_model", mode="before")
    @classmethod
    def sanitize_gemini_models(cls, v: Any) -> str:
        """Upgrade deprecated 2.5 models to current Gemini 3.8 Flash automatically."""
        if not v or "2.5" in str(v) or "gemini-pro" == str(v):
            return "gemini-3.8-flash"
        return str(v)

    # Meta / Instagram Graph API
    meta_app_id: str = Field(default="", description="Meta Developer App ID.")
    meta_app_secret: str = Field(default="", description="Meta Developer App Secret.")
    ig_user_id: str = Field(default="", description="Instagram Business/Creator Account ID.")
    ig_access_token: str = Field(default="", description="60-day long-lived User Access Token.")

    # Server
    api_host: str = Field(default="127.0.0.1", description="FastAPI host address.")
    api_port: int = Field(default=8000, description="FastAPI port.")
    ui_port: int = Field(default=5173, description="Vite preview UI port.")

    # Clustering & Grouping
    cluster_time_window_hours: float = Field(
        default=48.0,
        description="Max hours between photos in the same carousel cluster.",
    )
    cluster_gps_radius_km: float = Field(
        default=5.0,
        description="Max distance in km between photos in the same carousel cluster.",
    )
    carousel_min_slides: int = Field(
        default=1,
        description="Minimum slides to form a post/carousel.",
    )
    carousel_max_slides: int = Field(
        default=10,
        description="Maximum slides allowed in an Instagram carousel.",
    )


_SOURCE_ENV_KEYS = [
    "LOCAL_PHOTOS_DIR",
    "PHOTOS_ALBUM_NAME",
    "PHOTOS_LIBRARY_PATH",
    "INGEST_START_DATE",
    "INGEST_END_DATE",
    "INGEST_BATCH_MONTHS",
    "GEMINI_FLASH_MODEL",
    "GEMINI_PRO_MODEL",
]


def _clear_stale_env_overrides() -> None:
    import os

    for k in _SOURCE_ENV_KEYS:
        os.environ.pop(k, None)


_clear_stale_env_overrides()
settings = Settings()


def reload_settings() -> Settings:
    """Reload settings from .env dynamically at runtime."""
    global settings
    _clear_stale_env_overrides()
    settings = Settings()
    return settings
