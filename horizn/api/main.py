"""FastAPI application entry-point for the Horizn backend API."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from horizn.api.routes import carousels, ingest, publish, static
from horizn.config import settings
from horizn.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup tasks (DB init) then yield for the application lifetime."""
    await init_db()
    yield


app = FastAPI(
    title="Horizn API",
    description="Local backend for the Horizn Instagram carousel publishing service.",
    version="0.1.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS – allow the Vite dev server to call the API
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://localhost:{settings.ui_port}",
        f"http://127.0.0.1:{settings.ui_port}",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(ingest.router, prefix="/api/ingest", tags=["ingest"])
app.include_router(carousels.router, prefix="/api/carousels", tags=["carousels"])
app.include_router(carousels.router, prefix="/api", tags=["curation_alias"])  # allows /api/curate/run
app.include_router(publish.router, prefix="/api/publish", tags=["publish"])
app.include_router(static.router, prefix="/api/static", tags=["static"])


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health", tags=["meta"])
async def health() -> dict:
    """Return a simple liveness probe."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Static files – exported JPEGs served for the preview UI and tunnel
# ---------------------------------------------------------------------------
_export_dir = str(settings.export_dir)
os.makedirs(_export_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=_export_dir), name="static")
