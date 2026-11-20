"""Uses Gemini to determine the optimal visual narrative order for carousel slides."""

from __future__ import annotations

import asyncio
import io
import json
import logging

from google import genai
from google.genai import types
from PIL import Image

from horizn.config import settings

logger = logging.getLogger(__name__)

_MAX_THUMB_PX = 512


def _resize_to_bytes(path: str) -> bytes:
    """Open an image, resize so the longest side ≤ _MAX_THUMB_PX, return JPEG bytes."""
    img = Image.open(path).convert("RGB")
    w, h = img.size
    scale = _MAX_THUMB_PX / max(w, h)
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _build_prompt(n: int) -> str:
    return (
        f"You are a visual storytelling editor curating an Instagram carousel of {n} landscape "
        "scenery photos (provided in order 0 … N-1).\n\n"
        "Arrange them into the structure:\n"
        "  • Slide 0 – Hook: the single most striking, attention-grabbing image.\n"
        "  • Slides 1 … N-2 – Body: images that develop the visual story / journey.\n"
        "  • Slide N-1 – Closer: a satisfying, contemplative conclusion.\n\n"
        "Return ONLY valid JSON with this exact schema (no markdown fence, no extra keys):\n"
        '{"order": [<index>, ...], "rationale": ["<one sentence per slide>", ...]}\n\n'
        "Rules:\n"
        "- 'order' must be a permutation of 0 … N-1 (each index exactly once).\n"
        "- 'rationale' must have the same length as 'order'.\n"
        "- Do NOT wrap the JSON in a code fence."
    )


async def sequence_slides(photos: list[dict]) -> list[dict]:
    """
    Reorder *photos* using Gemini 2.5 Flash for optimal narrative flow.

    Hook (most striking) → Body (story development) → Closer.

    Falls back to the original order on any error.

    Parameters
    ----------
    photos:
        List of photo dicts containing at least ``export_path``.

    Returns
    -------
    Reordered list of photo dicts.
    """
    if len(photos) <= 1:
        return photos

    if not settings.gemini_api_key or settings.gemini_api_key.startswith("your_"):
        return photos

    try:
        client = genai.Client(api_key=settings.gemini_api_key)

        parts: list[types.Part] = [types.Part.from_text(text=_build_prompt(len(photos)))]
        for photo in photos:
            try:
                img_bytes = _resize_to_bytes(photo["export_path"])
                parts.append(types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"))
            except Exception as exc:
                logger.warning("Could not load image %s for sequencing: %s", photo.get("id"), exc)
                # Provide a 1×1 black pixel placeholder so index positions stay correct
                placeholder = io.BytesIO()
                Image.new("RGB", (1, 1)).save(placeholder, format="JPEG")
                parts.append(
                    types.Part.from_bytes(data=placeholder.getvalue(), mime_type="image/jpeg")
                )

        response = client.models.generate_content(
            model=settings.gemini_flash_model,
            contents=[types.Content(role="user", parts=parts)],
        )

        raw = response.text.strip()
        # Strip optional markdown code fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)

        order: list[int] = data["order"]
        # Validate: must be a permutation of 0 … n-1
        n = len(photos)
        if sorted(order) != list(range(n)):
            raise ValueError(f"Invalid order permutation: {order}")

        return [photos[i] for i in order]

    except Exception as exc:
        logger.warning("Gemini sequencing failed (%s); keeping original order.", exc)
        return photos
