"""Utilities for refreshing and checking 60-day Instagram Graph API access tokens."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import httpx

from horizn.config import settings

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"
ENV_PATH = Path(".env")


async def refresh_token() -> str:
    """Refresh the long-lived access token and update .env in-place."""
    token = settings.ig_access_token
    if not token:
        raise ValueError("IG_ACCESS_TOKEN is not configured in settings")

    logger.info("Requesting long-lived token refresh from Meta...")
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.get(
            f"{GRAPH_API_BASE}/oauth/access_token",
            params={
                "grant_type": "ig_refresh_token",
                "access_token": token,
            },
        )
        data = res.json()
        if "access_token" not in data:
            raise RuntimeError(f"Token refresh failed: {data}")

        new_token = data["access_token"]
        expires_in = data.get("expires_in", 5184000)  # ~60 days default
        logger.info("Token refreshed successfully (valid for ~%d days).", expires_in // 86400)

        # Update .env
        if ENV_PATH.exists():
            content = ENV_PATH.read_text(encoding="utf-8")
            if re.search(r"^IG_ACCESS_TOKEN=.*$", content, flags=re.MULTILINE):
                new_content = re.sub(
                    r"^IG_ACCESS_TOKEN=.*$",
                    f"IG_ACCESS_TOKEN={new_token}",
                    content,
                    flags=re.MULTILINE,
                )
            else:
                new_content = content.rstrip() + f"\nIG_ACCESS_TOKEN={new_token}\n"
            ENV_PATH.write_text(new_content, encoding="utf-8")
            logger.info(".env updated with refreshed IG_ACCESS_TOKEN.")

        return new_token


async def check_token_expiry() -> dict:
    """Check current token validity and user identity."""
    token = settings.ig_access_token
    if not token:
        return {"status": "unconfigured"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.get(
            f"{GRAPH_API_BASE}/me",
            params={"fields": "id,username", "access_token": token},
        )
        data = res.json()
        return data
