from __future__ import annotations

import re
from collections.abc import Iterable

from ..models import BoundingBox, DetectedPii, PiiType, TextElement


EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
CAPITALIZED_RE = re.compile(r"^[A-Z][a-z]{1,30}(?:[-'][A-Z][a-z]{1,30})?$")
NON_NAME_WORDS = {
    "board", "center", "cloud", "compliance", "content", "cross", "data", "department",
    "director", "enterprise", "executive", "governance", "information", "infrastructure",
    "inspection", "integration", "lead", "level", "network", "operations", "principal",
    "privacy", "report", "security", "senior", "services", "shared", "specialist", "systems",
    "technical", "threat", "unit", "advisor", "architect", "analyst", "engineer", "officer",
    "document", "directory", "regulatory", "corporate", "purpose", "scope", "classification",
    "assigned", "custodians", "responsibilities", "horizon", "audit", "issuing", "body", "status",
}


def _normalise(value: str) -> str:
    return " ".join(value.casefold().split())


def _union(bounds: list[BoundingBox]) -> BoundingBox:
    return BoundingBox(
        min(box.left for box in bounds),
        min(box.top for box in bounds),
        max(box.right for box in bounds),
        max(box.bottom for box in bounds),
    )


def _detect_page(
    words: list[TextElement],
    employee_patterns: Iterable[str],
    pii_types: tuple[PiiType, ...],
) -> list[DetectedPii]:
    detections: list[DetectedPii] = []
    emails: list[TextElement] = []
    if PiiType.EMAIL in pii_types:
        for word in words:
            if EMAIL_RE.fullmatch(word.text):
                detections.append(DetectedPii(PiiType.EMAIL, word.text, word.page_number, word.bounds))
                emails.append(word)

    if PiiType.EMPLOYEE_ID in pii_types:
        for word in words:
            if any(re.fullmatch(pattern, word.text) for pattern in employee_patterns):
                detections.append(DetectedPii(PiiType.EMPLOYEE_ID, word.text, word.page_number, word.bounds))

    if PiiType.NAME in pii_types:
        for first, second in zip(words, words[1:]):
            first_value = first.text.strip(".,:;()")
            second_value = second.text.strip(".,:;()")
            if not CAPITALIZED_RE.fullmatch(first_value) or not CAPITALIZED_RE.fullmatch(second_value):
                continue
            if first_value.casefold() in NON_NAME_WORDS or second_value.casefold() in NON_NAME_WORDS:
                continue
            if abs(first.bounds.top - second.bounds.top) > 28:
                continue
            detections.append(
                DetectedPii(
                    PiiType.NAME,
                    f"{first_value} {second_value}",
                    first.page_number,
                    _union([first.bounds, second.bounds]),
                )
            )
    return detections


def detect_pii(
    elements: Iterable[TextElement],
    protected_persons: Iterable[str],
    employee_patterns: Iterable[str],
    pii_types: tuple[PiiType, ...] = (PiiType.NAME,),
) -> list[DetectedPii]:
    by_page: dict[int, list[TextElement]] = {}
    for element in elements:
        by_page.setdefault(element.page_number, []).append(element)

    protected = {_normalise(person) for person in protected_persons}
    results: list[DetectedPii] = []
    for words in by_page.values():
        page_detections = _detect_page(words, employee_patterns, pii_types)
        for detection in page_detections:
            protected_match = _normalise(detection.value) in protected
            results.append(
                DetectedPii(
                    detection.pii_type,
                    detection.value,
                    detection.page_number,
                    detection.bounds,
                    protected=protected_match,
                )
            )
    return results