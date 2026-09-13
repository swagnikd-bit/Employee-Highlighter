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
        rectangles = [pymupdf.Rect(box.left, box.top, box.right, box.bottom)
                      for box in (detection.word_bounds or (detection.bounds,))]
        if any(
            protected.page_number == detection.page_number and protected.protected
            and rectangle.intersects(pymupdf.Rect(box.left, box.top, box.right, box.bottom))
            for protected in detections
            for box in (protected.word_bounds or (protected.bounds,))
            for rectangle in rectangles
        ):
            raise RuntimeError("An eligible highlight overlaps protected information; review detections")
        annotation = page.add_highlight_annot([rectangle.quad for rectangle in rectangles])
        annotation.set_colors(stroke=color)
        annotation.set_opacity(opacity)
        annotation.update()
        count += 1
    return count
