"""Generates Instagram captions and hashtags for carousels using Gemini."""

from __future__ import annotations

import asyncio
import io
import logging
import re
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image

from horizn.config import settings

logger = logging.getLogger(__name__)

_FALLBACK_CAPTION = "Beautiful scenery."
_FALLBACK_HASHTAGS = ["#travel", "#nature", "#landscape"]

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
    """Parse the Gemini response into (caption, hashtags) robustly handling dashes, fences, and newlines."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
        cleaned = cleaned.strip()

    hashtags: list[str] = []
    caption_lines: list[str] = []

    for line in cleaned.splitlines():
        trimmed = line.strip()
        if trimmed == "---":
            continue
        if trimmed.upper().startswith("HASHTAGS:"):
            raw_tags = trimmed.split(":", 1)[1].strip()
            hashtags.extend([t for t in raw_tags.split() if t.startswith("#")])
        elif trimmed and all(w.startswith("#") for w in trimmed.split()):
            hashtags.extend(trimmed.split())
        else:
            caption_lines.append(line)

    caption = "\n".join(caption_lines).strip()
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

        # Call Gemini with retry and adaptive backoff for rate limits
        last_error = None
        for attempt in range(1, 5):
            try:
                # Use Flash model on attempts >= 2 if Pro is experiencing a rate limit or demand spike
                model_to_use = (
                    settings.gemini_pro_model if attempt == 1 else settings.gemini_flash_model
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
                err_str = str(exc)
                is_rate_limit = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str

                # Determine backoff delay: check if API specified retry delay, else default to 6s+
                delay = attempt * 2.5
                match = re.search(r"retry in (\d+(?:\.\d+)?)s", err_str, re.IGNORECASE)
                if match:
                    delay = float(match.group(1)) + 1.5
                elif is_rate_limit:
                    delay = max(delay, 6.0 * attempt)

                logger.warning(
                    "Caption generation attempt %d failed (%s); retrying in %.1fs...",
                    attempt,
                    exc,
                    delay,
                )
                if attempt < 4:
                    await asyncio.sleep(delay)

        if last_error:
            logger.warning("All caption generation attempts failed (%s); using fallback.", last_error)
        return _FALLBACK_CAPTION, _FALLBACK_HASHTAGS

    except Exception as exc:
        logger.warning("Caption generation failed (%s); using fallback.", exc)
        return _FALLBACK_CAPTION, _FALLBACK_HASHTAGS


def _build_refine_prompt(
    current_caption: str | None,
    instruction: str | None,
    mode: str,
    location_hint: str | None,
) -> str:
    parts = [
        "You are an expert social media copywriter and creative photographer assistant specialising in Instagram travel and candid mobile photography.",
        "Your task is to write or refine an evocative caption and relevant hashtags for an Instagram carousel post based on the attached photos and the user's instructions.",
    ]
    if location_hint:
        parts.append(f"Location / Context: {location_hint}")

    if mode == "scratch":
        parts.append("\nGoal: Write an entirely fresh, engaging caption from scratch for this set of photos.")
        if instruction:
            parts.append(f"User's creative guidance: \"{instruction}\"")
    else:  # refine mode
        if current_caption:
            parts.append(f"\nExisting draft caption:\n\"\"\"{current_caption}\"\"\"")
        if instruction:
            parts.append(f"\nUser's edit instruction / feedback:\n\"{instruction}\"")
        else:
            parts.append("\nGoal: Polish, elevate, and enhance the draft caption while preserving its core feeling.")

    parts.append(
        "\nFormat your entire response as follows (replace placeholders):\n"
        "<Your caption here>\n"
        "---\n"
        "HASHTAGS: #tag1 #tag2 #tag3 #tag4 #tag5 #tag6 #tag7 #tag8 #tag9 #tag10 #tag11 #tag12\n\n"
        "Rules:\n"
        "- Match the tone, length, and specifics requested in the user's instruction precisely (e.g. humorous, poetic, short & punchy, or focusing on a specific element).\n"
        "- Keep it natural, human, and authentic (avoid overly generic marketing buzzwords).\n"
        "- The separator line must be exactly three dashes: ---\n"
        "- Hashtags must be on a single line, prefixed with HASHTAGS: and each tag starts with #.\n"
        "- Do not include markdown code fences (```) or any other commentary."
    )
    return "\n".join(parts)


async def refine_or_generate_caption(
    photos: list[dict],
    current_caption: str | None = None,
    instruction: str | None = None,
    location_hint: str | None = None,
    mode: str = "refine",
) -> tuple[str, list[str]]:
    """Refine an existing caption with user guidance or generate a fresh caption from scratch using Gemini.

    Parameters
    ----------
    photos:
        List of photo dicts in the carousel.
    current_caption:
        The current caption in the draft, if refining.
    instruction:
        User's prompt or feedback (e.g., 'Make it more poetic and shorter', 'Focus on the street tea stall').
    location_hint:
        Optional location or GPS hint.
    mode:
        'refine' to modify existing caption, or 'scratch' to build fresh.
    """
    if not settings.gemini_api_key or settings.gemini_api_key.startswith("your_"):
        return current_caption or _FALLBACK_CAPTION, _FALLBACK_HASHTAGS

    try:
        client = genai.Client(api_key=settings.gemini_api_key)

        prompt_text = _build_refine_prompt(current_caption, instruction, mode, location_hint)
        parts: list[types.Part] = [types.Part.from_text(text=prompt_text)]

        # Attach up to 3 representative photos from the carousel so Gemini has full visual grounding
        n = len(photos)
        if n > 0:
            indices = [0]
            if n > 2:
                indices.append(n // 2)
            if n > 1:
                indices.append(n - 1)
            seen: set[int] = set()
            for idx in indices:
                if idx not in seen and idx < n:
                    seen.add(idx)
                    p = photos[idx]
                    path = p.get("export_path")
                    if path:
                        try:
                            img_bytes = _photo_to_jpeg_bytes(path)
                            parts.append(types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"))
                        except Exception as exc:
                            logger.warning("Could not attach slide %s for AI caption: %s", p.get("id"), exc)

        last_error = None
        for attempt in range(1, 4):
            try:
                # Use Flash model for fast responsive AI editing
                model_to_use = settings.gemini_flash_model
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model_to_use,
                    contents=[types.Content(role="user", parts=parts)],
                )

                raw_text = response.text.strip() if response.text else ""
                caption, hashtags = _parse_response(raw_text)
                if caption:
                    return caption, hashtags or _FALLBACK_HASHTAGS

            except Exception as exc:
                last_error = exc
                err_str = str(exc)
                is_rate_limit = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str
                delay = attempt * 2.0
                match = re.search(r"retry in (\d+(?:\.\d+)?)s", err_str, re.IGNORECASE)
                if match:
                    delay = float(match.group(1)) + 1.0
                elif is_rate_limit:
                    delay = max(delay, 5.0)

                logger.warning("AI caption assistant attempt %d failed (%s); retrying in %.1fs...", attempt, exc, delay)
                if attempt < 3:
                    await asyncio.sleep(delay)

        if last_error:
            logger.warning("All AI caption assistant attempts failed (%s).", last_error)
        return current_caption or _FALLBACK_CAPTION, _FALLBACK_HASHTAGS

    except Exception as exc:
        logger.warning("refine_or_generate_caption failed (%s).", exc)
        return current_caption or _FALLBACK_CAPTION, _FALLBACK_HASHTAGS
