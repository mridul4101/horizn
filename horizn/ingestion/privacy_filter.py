"""Apple Vision framework filter to detect and exclude photos containing faces/persons."""

from __future__ import annotations

import logging
from typing import Tuple

from horizn.config import settings

logger = logging.getLogger(__name__)

# Thresholds read from settings
FACE_CONFIDENCE_THRESHOLD: float = settings.face_confidence_threshold
MIN_FACE_AREA_RATIO: float = settings.min_face_area_ratio
# Human body bounding-box area ratio above which the photo is excluded
MIN_HUMAN_AREA_RATIO: float = 0.15


def _run_vision_request(image_path: str, request):  # type: ignore[no-untyped-def]
    """Execute a single VNRequest against *image_path* and return its results."""
    import Vision  # pyobjc-framework-Vision  # noqa: PLC0415
    import Foundation  # pyobjc-framework-Foundation  # noqa: PLC0415

    url = Foundation.NSURL.fileURLWithPath_(image_path)
    handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, None)
    handler.performRequests_error_([request], None)
    return request.results()


def _bounding_box_area(bb) -> float:  # type: ignore[return]
    """Return the normalised bounding-box area (0–1) for a VNObservation."""
    # bb is an NSRect / CGRect with .size.width / .size.height
    try:
        w = bb.size.width
        h = bb.size.height
        return float(w * h)
    except Exception:
        return 0.0


def is_landscape_photo(image_path: str) -> Tuple[bool, str]:
    """Return (passed, reason) where passed=True means the photo is acceptable.

    Privacy rules applied (in order):
    1. Prominent face  → (False, "prominent_face")
    2. Prominent person body → (False, "prominent_person")
    3. Everything passes → (True, "landscape")

    OSError and Vision framework errors are caught and logged; on error the photo
    is *accepted* (True) so the caller decides what to do next.
    """
    try:
        import Vision  # noqa: PLC0415

        # ------------------------------------------------------------------
        # 1. Face detection
        # ------------------------------------------------------------------
        face_request = Vision.VNDetectFaceRectanglesRequest.alloc().init()
        face_results = _run_vision_request(image_path, face_request)

        if face_results:
            for obs in face_results:
                confidence = float(obs.confidence()) if hasattr(obs, "confidence") else 1.0
                bb = obs.boundingBox()
                area_ratio = _bounding_box_area(bb)
                if confidence >= FACE_CONFIDENCE_THRESHOLD and area_ratio >= MIN_FACE_AREA_RATIO:
                    logger.debug(
                        "Excluding %s: face confidence=%.2f area_ratio=%.4f",
                        image_path,
                        confidence,
                        area_ratio,
                    )
                    return (False, "prominent_face")

        # ------------------------------------------------------------------
        # 2. Human body detection
        # ------------------------------------------------------------------
        human_request = Vision.VNDetectHumanRectanglesRequest.alloc().init()
        human_results = _run_vision_request(image_path, human_request)

        if human_results:
            for obs in human_results:
                bb = obs.boundingBox()
                area = _bounding_box_area(bb)
                if area > MIN_HUMAN_AREA_RATIO:
                    logger.debug(
                        "Excluding %s: human body area_ratio=%.4f",
                        image_path,
                        area,
                    )
                    return (False, "prominent_person")

    except OSError as exc:
        logger.warning("OSError running Vision on %s: %s — accepting photo", image_path, exc)
        return (True, "landscape")
    except Exception as exc:  # Vision framework / pyobjc errors
        logger.warning(
            "Vision framework error on %s: %s — accepting photo", image_path, exc
        )
        return (True, "landscape")

    return (True, "landscape")
