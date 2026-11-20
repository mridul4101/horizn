"""Async SQLite database helpers: connection factory and schema initialisation."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import aiosqlite

DB_PATH = Path("./data/horizn.db")

_CREATE_PHOTOS = """
CREATE TABLE IF NOT EXISTS photos (
  id TEXT PRIMARY KEY,
  filepath TEXT NOT NULL,
  taken_at DATETIME,
  lat REAL,
  lon REAL,
  sharpness REAL,
  aspect_ratio TEXT,
  is_landscape BOOLEAN DEFAULT 0,
  export_path TEXT,
  duplicate_of TEXT REFERENCES photos(id) ON DELETE SET NULL,
  ingested_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

_CREATE_CAROUSELS = """
CREATE TABLE IF NOT EXISTS carousels (
  id TEXT PRIMARY KEY,
  status TEXT DEFAULT 'draft',
  aspect_ratio TEXT,
  caption TEXT,
  hashtags TEXT,
  ig_media_id TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  published_at DATETIME
);
"""

_CREATE_CAROUSEL_SLIDES = """
CREATE TABLE IF NOT EXISTS carousel_slides (
  carousel_id TEXT REFERENCES carousels(id),
  photo_id TEXT REFERENCES photos(id),
  position INTEGER NOT NULL,
  caption TEXT,
  PRIMARY KEY (carousel_id, photo_id)
);
"""

_CREATE_PUBLISH_LOG = """
CREATE TABLE IF NOT EXISTS publish_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  carousel_id TEXT REFERENCES carousels(id),
  event TEXT,
  detail TEXT,
  ts DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Async context manager that yields an aiosqlite connection with WAL mode enabled."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL;")
        await conn.execute("PRAGMA foreign_keys=ON;")
        yield conn


async def init_db() -> None:
    """Create all application tables if they do not already exist."""
    async with get_db() as conn:
        await conn.execute(_CREATE_PHOTOS)
        await conn.execute(_CREATE_CAROUSELS)
        await conn.execute(_CREATE_CAROUSEL_SLIDES)
        await conn.execute(_CREATE_PUBLISH_LOG)

        # Migration: ensure duplicate_of column exists on existing databases
        try:
            await conn.execute("ALTER TABLE photos ADD COLUMN duplicate_of TEXT REFERENCES photos(id)")
        except Exception:
            pass

        await conn.commit()
