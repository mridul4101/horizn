"""FastAPI router for static file access and export downloads."""

from __future__ import annotations

from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from horizn.config import settings

router = APIRouter()


@router.get("/exports/{filename}")
async def get_export_file(filename: str) -> FileResponse:
    """Retrieve an exported photo by filename."""
    file_path = settings.export_dir / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, media_type="image/jpeg")
