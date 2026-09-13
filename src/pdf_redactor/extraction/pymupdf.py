from __future__ import annotations

from pathlib import Path

import pymupdf

from ..models import BoundingBox, TextElement


def extract_words(document: pymupdf.Document) -> list[TextElement]:
    elements: list[TextElement] = []
    for page_number, page in enumerate(document, start=1):
        for word in page.get_text("words", sort=True):
            left, top, right, bottom, text = word[:5]
            if text.strip():
                elements.append(
                    TextElement(
                        page_number=page_number,
                        text=text,
                        bounds=BoundingBox(left, top, right, bottom),
                    )
                )
    return elements