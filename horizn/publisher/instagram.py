"""Publishes carousel drafts or single posts to Instagram via the Meta Graph API."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Coroutine, Optional

import httpx
from dotenv import dotenv_values, load_dotenv, set_key
from PIL import Image

from horizn.config import Settings, settings
from horizn.database import get_db
from horizn.publisher.tunnel import ephemeral_tunnel

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"


def _get_fresh_credentials() -> tuple[str, str, str, str, int]:
    """Read latest credentials directly from .env on disk, bypassing stale os.environ."""
    env_path = Path(".env")
    if env_path.exists():
        try:
            load_dotenv(dotenv_path=env_path, override=True)
        except Exception as exc:
            logger.warning("Could not reload .env: %s", exc)

    env_vals = dotenv_values(".env") if env_path.exists() else {}
    current_settings = Settings()

    ig_user_id = str(env_vals.get("IG_USER_ID") or current_settings.ig_user_id or "").strip().strip("'\"")
    ig_access_token = str(env_vals.get("IG_ACCESS_TOKEN") or current_settings.ig_access_token or "").strip().strip("'\"")
    meta_app_id = str(env_vals.get("META_APP_ID") or current_settings.meta_app_id or "").strip().strip("'\"")
    meta_app_secret = str(env_vals.get("META_APP_SECRET") or current_settings.meta_app_secret or "").strip().strip("'\"")
    api_port = current_settings.api_port

    return ig_user_id, ig_access_token, meta_app_id, meta_app_secret, api_port


async def _ensure_long_lived_token(access_token: str, app_id: str | None, app_secret: str | None) -> str:
    """Attempt to exchange a short-lived user token for a 60-day long-lived token.
    If exchange succeeds, also persists the 60-day token back to .env so it survives.
    """
    if not app_id or not app_secret or not access_token:
        return access_token
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{GRAPH_API_BASE}/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": app_id,
                    "client_secret": app_secret,
                    "fb_exchange_token": access_token,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                if "access_token" in data:
                    new_token = data["access_token"]
                    logger.info("Successfully upgraded Instagram access token to 60-day long-lived token.")
                    try:
                        env_path = Path(".env")
                        if env_path.exists():
                            set_key(str(env_path), "IG_ACCESS_TOKEN", new_token)
                            os.environ["IG_ACCESS_TOKEN"] = new_token
                    except Exception as pe:
                        logger.warning("Could not persist upgraded token to .env: %s", pe)
                    return new_token
    except Exception as exc:
        logger.debug("Token exchange skipped: %s", exc)
    return access_token


async def _log_event(
    carousel_id: str,
    event: str,
    detail: str,
    status_callback: Optional[Callable[[str, str], Coroutine[Any, Any, None]]] = None,
) -> None:
    """Record an audit log entry in the publish_log table and invoke the callback if given."""
    logger.info("[%s] %s: %s", carousel_id, event, detail)
    try:
        async with get_db() as conn:
            await conn.execute(
                "INSERT INTO publish_log (carousel_id, event, detail) VALUES (?, ?, ?)",
                (carousel_id, event, detail),
            )
            await conn.commit()
    except Exception as exc:
        logger.warning("Could not write to publish_log: %s", exc)

    if status_callback:
        try:
            await status_callback(event, detail)
        except Exception as exc:
            logger.warning("status_callback error: %s", exc)


def _prepare_image_for_instagram(export_path: str) -> str:
    """Pre-scale and optimize an image for Instagram publishing requirements.

    Meta Graph API limitations:
    - Max file size: 8 MB (strictly enforced)
    - Max resolution: 1440px max dimension recommended
    - Image format: JPEG sRGB

    Returns the filename of the prepared JPEG located in settings.export_dir.
    """
    src_path = Path(export_path)
    if not src_path.is_absolute():
        src_path = settings.export_dir / src_path
    if not src_path.exists():
        src_path = settings.export_dir / src_path.name

    out_name = f"{src_path.stem}_ig.jpg"
    out_path = settings.export_dir / out_name

    with Image.open(src_path) as img:
        img = img.convert("RGB")
        w, h = img.size
        max_dim = max(w, h)
        if max_dim > 1440:
            scale = 1440.0 / max_dim
            new_w = int(w * scale)
            new_h = int(h * scale)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(out_path), format="JPEG", quality=90, optimize=True)

    return out_name


async def publish_carousel(
    carousel_id: str,
    status_callback: Optional[Callable[[str, str], Coroutine[Any, Any, None]]] = None,
) -> str:
    """Publish a carousel draft (or single photo) to Instagram using the Meta Graph API.

    Steps:
    1. Fetch carousel and ordered slides from SQLite.
    2. Start an ephemeral cloudflared tunnel exposing local /static exports.
    3. Upload each slide as an item container (or single post).
    4. Create the carousel container (if > 1 slide).
    5. Publish the container and poll until finished.
    6. Update carousel record with ig_media_id, status='published', published_at.
    """
    await _log_event(carousel_id, "start", "Initiating publish sequence", status_callback)

    # 1. Fetch carousel & slides
    async with get_db() as conn:
        async with conn.execute(
            "SELECT * FROM carousels WHERE id = ?", (carousel_id,)
        ) as cursor:
            carousel = await cursor.fetchone()

        if not carousel:
            err = f"Carousel {carousel_id} not found"
            await _log_event(carousel_id, "error", err, status_callback)
            raise ValueError(err)

        async with conn.execute(
            """
            SELECT cs.position, cs.caption as slide_caption, p.id as photo_id, p.export_path
            FROM carousel_slides cs
            JOIN photos p ON cs.photo_id = p.id
            WHERE cs.carousel_id = ?
            ORDER BY cs.position ASC
            """,
            (carousel_id,),
        ) as cursor:
            slides = [dict(row) for row in await cursor.fetchall()]

    if not slides:
        err = f"Carousel {carousel_id} has no slides"
        await _log_event(carousel_id, "error", err, status_callback)
        raise ValueError(err)

    # Dynamically load latest settings directly from .env (avoiding stale os.environ)
    ig_user_id, raw_token, meta_app_id, meta_app_secret, api_port = _get_fresh_credentials()
    if not ig_user_id or not raw_token:
        err = "Missing IG_USER_ID or IG_ACCESS_TOKEN in environment"
        await _log_event(carousel_id, "error", err, status_callback)
        raise ValueError(err)

    # Automatically upgrade to 60-day token if possible
    access_token = await _ensure_long_lived_token(
        raw_token,
        meta_app_id,
        meta_app_secret,
    )

    # Prepare caption & hashtags
    full_caption = carousel["caption"] or ""
    if carousel["hashtags"]:
        try:
            tags = json.loads(carousel["hashtags"])
            if tags:
                full_caption += "\n\n" + " ".join(tags)
        except Exception:
            pass

    local_url = f"http://127.0.0.1:{api_port}"

    async with ephemeral_tunnel(local_url) as tunnel_url:
        await _log_event(carousel_id, "tunnel_ready", f"Public tunnel active: {tunnel_url}", status_callback)

        async with httpx.AsyncClient(timeout=60.0) as client:
            # If single photo post
            if len(slides) == 1:
                slide = slides[0]
                filename = await asyncio.to_thread(_prepare_image_for_instagram, slide["export_path"])
                img_url = f"{tunnel_url}/static/{filename}"
                await _log_event(carousel_id, "upload", f"Uploading single image: {img_url}", status_callback)

                res = await client.post(
                    f"{GRAPH_API_BASE}/{ig_user_id}/media",
                    params={
                        "image_url": img_url,
                        "caption": full_caption,
                        "access_token": access_token,
                    },
                )
                data = res.json()
                if "id" not in data:
                    err = f"Failed to create single photo container: {data}"
                    await _log_event(carousel_id, "error", err, status_callback)
                    raise RuntimeError(err)

                container_id = data["id"]

            else:
                # 2+ slides: Upload each carousel slide item
                item_container_ids: list[str] = []
                for idx, slide in enumerate(slides):
                    filename = await asyncio.to_thread(_prepare_image_for_instagram, slide["export_path"])
                    img_url = f"{tunnel_url}/static/{filename}"
                    await _log_event(
                        carousel_id,
                        "upload_slide",
                        f"Uploading slide {idx + 1}/{len(slides)}",
                        status_callback,
                    )

                    res = await client.post(
                        f"{GRAPH_API_BASE}/{ig_user_id}/media",
                        params={
                            "image_url": img_url,
                            "is_carousel_item": "true",
                            "access_token": access_token,
                        },
                    )
                    data = res.json()
                    if "id" not in data:
                        err = f"Failed slide item {idx + 1}: {data}"
                        await _log_event(carousel_id, "error", err, status_callback)
                        raise RuntimeError(err)

                    item_container_ids.append(data["id"])

                # Create carousel container
                await _log_event(
                    carousel_id,
                    "create_carousel",
                    f"Creating carousel container with {len(item_container_ids)} items",
                    status_callback,
                )
                res = await client.post(
                    f"{GRAPH_API_BASE}/{ig_user_id}/media",
                    params={
                        "media_type": "CAROUSEL",
                        "children": ",".join(item_container_ids),
                        "caption": full_caption,
                        "access_token": access_token,
                    },
                )
                data = res.json()
                if "id" not in data:
                    err = f"Failed to create carousel container: {data}"
                    await _log_event(carousel_id, "error", err, status_callback)
                    raise RuntimeError(err)

                container_id = data["id"]

            # Poll container status until FINISHED
            await _log_event(carousel_id, "processing", f"Polling container {container_id} status", status_callback)
            for _ in range(12):
                await asyncio.sleep(5)
                stat_res = await client.get(
                    f"{GRAPH_API_BASE}/{container_id}",
                    params={"fields": "status_code,status", "access_token": access_token},
                )
                stat_data = stat_res.json()
                code = stat_data.get("status_code", "").upper()
                if code == "FINISHED":
                    break
                elif code == "ERROR":
                    err = f"Container processing error: {stat_data}"
                    await _log_event(carousel_id, "error", err, status_callback)
                    raise RuntimeError(err)

            # Publish container
            await _log_event(carousel_id, "publishing", "Publishing container to Instagram feed", status_callback)
            pub_res = await client.post(
                f"{GRAPH_API_BASE}/{ig_user_id}/media_publish",
                params={"creation_id": container_id, "access_token": access_token},
            )
            pub_data = pub_res.json()
            ig_media_id = pub_data.get("id")

            if not ig_media_id:
                # Meta occasionally publishes the post successfully but returns an anti-spam or velocity warning
                # (e.g. error code 4, error_subcode 2207051 'action is blocked') on the response.
                # Verify by checking the account's most recent media items.
                logger.warning("media_publish returned error %s; checking if media was actually published...", pub_data)
                try:
                    await asyncio.sleep(2.0)
                    recent_res = await client.get(
                        f"{GRAPH_API_BASE}/{ig_user_id}/media",
                        params={"fields": "id,caption", "access_token": access_token, "limit": 3},
                    )
                    if recent_res.status_code == 200:
                        recent_data = recent_res.json().get("data", [])
                        for item in recent_data:
                            # Match against the caption text
                            item_cap = (item.get("caption") or "").strip()
                            clean_cap = full_caption.strip()
                            if item_cap and clean_cap and (
                                clean_cap[:40] in item_cap or item_cap[:40] in clean_cap
                            ):
                                ig_media_id = item["id"]
                                logger.info(
                                    "Verified post was actually published despite Meta warning! ig_media_id: %s",
                                    ig_media_id,
                                )
                                break
                except Exception as check_exc:
                    logger.warning("Could not verify recent media: %s", check_exc)

            if not ig_media_id:
                err = f"Failed to publish media: {pub_data}"
                await _log_event(carousel_id, "error", err, status_callback)
                raise RuntimeError(err)
            now_iso = datetime.now(timezone.utc).isoformat()

            async with get_db() as conn:
                await conn.execute(
                    """
                    UPDATE carousels
                    SET status = 'published', ig_media_id = ?, published_at = ?
                    WHERE id = ?
                    """,
                    (ig_media_id, now_iso, carousel_id),
                )
                await conn.commit()

            await _log_event(
                carousel_id,
                "published",
                f"Successfully published! Instagram Media ID: {ig_media_id}",
                status_callback,
            )
            return ig_media_id
