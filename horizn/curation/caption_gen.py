"""Generates Instagram captions and hashtags for carousels using Gemini."""

from __future__ import annotations

import asyncio
import io
import logging

from google import genai
from google.genai import types
from PIL import Image

from horizn.config import settings

logger = logging.getLogger(__name__)

_FALLBACK_CAPTION = "Beautiful scenery."
_FALLBACK_HASHTAGS = ["#travel", "#nature", "#landscape"]


from pathlib import Path

_MAX_CAPTION_IMG_PX = 768


def _photo_to_jpeg_bytes(path: str) -> bytes:
    """Read an image from *path*, resize to max 768px for fast AI captioning, and return JPEG bytes."""
    p = Path(path)
    if not p.exists():
        alt = Path(settings.export_dir) / p.name
        if alt.exists():
            p = alt
    img = Image.open(p).convert("RGB")
    w, h = img.size
    scale = _MAX_CAPTION_IMG_PX / max(w, h)
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _build_prompt(location_hint: str | None, theme_hint: str | None = None) -> str:
    lines = []
    if location_hint:
        lines.append(f"Location: {location_hint}.")
    if theme_hint:
        lines.append(f"Visual Theme: {theme_hint}.")
    context = "\n".join(lines) + "\n\n" if lines else ""
    return (
        "You are a creative social-media copywriter specialising in travel and landscape "
        "photography.\n\n"
        f"{context}"
        "Write an evocative Instagram caption (2–4 sentences) for the scenery carousel shown "
        "in the attached photos, then provide exactly 15 relevant hashtags.\n\n"
        "Format your entire response as follows (replace the placeholders):\n"
        "<Your evocative caption here.>\n"
        "---\n"
        "HASHTAGS: #tag1 #tag2 #tag3 #tag4 #tag5 #tag6 #tag7 #tag8 #tag9 #tag10 "
        "#tag11 #tag12 #tag13 #tag14 #tag15\n\n"
        "Rules:\n"
        "- The separator line must be exactly three dashes: ---\n"
        "- Hashtags must be on a single line, prefixed with HASHTAGS: and each tag starts with #.\n"
        "- Do not add any other text or markdown."
    )


def _parse_response(text: str) -> tuple[str, list[str]]:
    """
    Parse the Gemini response into (caption, hashtags).

    Expected format::

        Evocative caption text here.
        ---
        HASHTAGS: #tag1 #tag2 ...
    """
    parts = text.split("---", maxsplit=1)
    caption = parts[0].strip()

    hashtags: list[str] = []
    if len(parts) > 1:
        rest = parts[1].strip()
        for line in rest.splitlines():
            if line.upper().startswith("HASHTAGS:"):
                raw_tags = line.split(":", 1)[1].strip()
                hashtags = [t for t in raw_tags.split() if t.startswith("#")]
                break

    return caption, hashtags


async def generate_caption(
    photos: list[dict],
    location_hint: str | None,
) -> tuple[str, list[str]]:
    """
    Generate an Instagram caption and 15 hashtags using Gemini 2.5 Pro.

    Up to three representative photos (first, middle, last) are attached as
    inline JPEG bytes.  Returns a ``(caption, hashtags)`` tuple.

    Falls back to ``(_FALLBACK_CAPTION, _FALLBACK_HASHTAGS)`` on any error.

    Parameters
    ----------
    photos:
        Ordered list of photo dicts with at least an ``export_path`` key.
    location_hint:
        Optional human-readable location string to include in the prompt.
    """
    n = len(photos)
    if n == 0:
        return _FALLBACK_CAPTION, _FALLBACK_HASHTAGS

    if not settings.gemini_api_key or settings.gemini_api_key.startswith("your_"):
        return _FALLBACK_CAPTION, _FALLBACK_HASHTAGS

    try:
        client = genai.Client(api_key=settings.gemini_api_key)

        # Select up to 3 representative photos: first, middle, last
        representative_indices: list[int] = []
        n = len(photos)
        if n == 0:
            return _FALLBACK_CAPTION, _FALLBACK_HASHTAGS
        representative_indices.append(0)
        if n > 2:
            representative_indices.append(n // 2)
        if n > 1:
            representative_indices.append(n - 1)
        # Deduplicate while preserving order
        seen: set[int] = set()
        rep_indices: list[int] = []
        for idx in representative_indices:
            if idx not in seen:
                seen.add(idx)
                rep_indices.append(idx)

        theme = photos[0].get("_ai_theme") if photos else None
        parts: list[types.Part] = [types.Part.from_text(text=_build_prompt(location_hint, theme))]
        for idx in rep_indices:
            photo = photos[idx]
            try:
                img_bytes = _photo_to_jpeg_bytes(photo["export_path"])
                parts.append(types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"))
            except Exception as exc:
                logger.warning(
                    "Could not attach image %s for caption generation: %s",
                    photo.get("id"),
                    exc,
                )

        # Call Gemini with retry and exponential backoff
        last_error = None
        for attempt in range(1, 4):
            try:
                # Use Flash model as fallback on 3rd attempt if Pro is experiencing a demand spike
                model_to_use = (
                    settings.gemini_pro_model if attempt < 3 else settings.gemini_flash_model
                )
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model_to_use,
                    contents=[types.Content(role="user", parts=parts)],
                )

                raw_text = response.text.strip() if response.text else ""
                caption, hashtags = _parse_response(raw_text)

                if caption and caption != _FALLBACK_CAPTION:
                    return caption, hashtags or _FALLBACK_HASHTAGS

            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Caption generation attempt %d failed (%s); retrying in %ss...",
                    attempt,
                    exc,
                    attempt * 1.5,
                )
                if attempt < 3:
                    await asyncio.sleep(attempt * 1.5)

        if last_error:
            logger.warning("All caption generation attempts failed (%s); using fallback.", last_error)
        return _FALLBACK_CAPTION, _FALLBACK_HASHTAGS

    except Exception as exc:
        logger.warning("Caption generation failed (%s); using fallback.", exc)
        return _FALLBACK_CAPTION, _FALLBACK_HASHTAGS
