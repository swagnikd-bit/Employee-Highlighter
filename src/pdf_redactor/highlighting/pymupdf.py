from __future__ import annotations

import pymupdf

from ..models import DetectedPii


def add_highlights(
    document: pymupdf.Document,
    detections: list[DetectedPii],
    color: tuple[float, float, float],
    opacity: float,
) -> int:
    count = 0
    for detection in detections:
        if detection.protected:
            continue
        page = document[detection.page_number - 1]
        rectangle = pymupdf.Rect(
            detection.bounds.left,
            detection.bounds.top,
            detection.bounds.right,
            detection.bounds.bottom,
        )
        if any(
            protected.page_number == detection.page_number and protected.protected
            and rectangle.intersects(pymupdf.Rect(protected.bounds.left, protected.bounds.top,
                                                protected.bounds.right, protected.bounds.bottom))
            for protected in detections
        ):
            raise RuntimeError("An eligible highlight overlaps protected information; review detections")
        annotation = page.add_highlight_annot(rectangle)
        annotation.set_colors(stroke=color)
        annotation.set_opacity(opacity)
        annotation.update()
        count += 1
    return count
