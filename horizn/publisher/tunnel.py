"""Manages an ephemeral cloudflared Quick Tunnel for publishing to Instagram."""

from __future__ import annotations

import asyncio
import logging
import re
from contextlib import asynccontextmanager
from typing import AsyncGenerator

logger = logging.getLogger(__name__)


@asynccontextmanager
async def ephemeral_tunnel(local_url: str) -> AsyncGenerator[str, None]:
    """Start a cloudflared Quick Tunnel, yield its public HTTPS URL, and guarantee teardown.

    Parameters
    ----------
    local_url:
        The local server URL to expose, e.g. "http://127.0.0.1:8000".

    Yields
    ------
    str:
        The temporary public HTTPS URL (e.g. "https://xxxx.trycloudflare.com").
    """
    logger.info("Spawning ephemeral cloudflared tunnel for %s...", local_url)
    proc = await asyncio.create_subprocess_exec(
        "cloudflared",
        "tunnel",
        "--url",
        local_url,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )

    public_url: str | None = None

    try:
        # Read lines from stderr where cloudflared prints the trycloudflare.com URL
        assert proc.stderr is not None
        while True:
            line_bytes = await asyncio.wait_for(proc.stderr.readline(), timeout=30.0)
            if not line_bytes:
                break
            line = line_bytes.decode("utf-8", errors="replace")
            logger.debug("[cloudflared] %s", line.strip())
            match = re.search(r"https://[a-zA-Z0-9\-]+\.trycloudflare\.com", line)
            if match:
                public_url = match.group(0)
                break

        if not public_url:
            proc.kill()
            await proc.wait()
            raise RuntimeError("cloudflared tunnel URL not found in output within 30s")

        logger.info("Tunnel established: %s", public_url)
        yield public_url

    finally:
        logger.info("Tearing down ephemeral cloudflared tunnel...")
        try:
            proc.kill()
            await proc.wait()
            logger.info("cloudflared tunnel process terminated successfully.")
        except Exception as exc:
            logger.warning("Error during cloudflared teardown: %s", exc)
