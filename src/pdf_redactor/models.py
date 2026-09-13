from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class PiiType(StrEnum):
    NAME = "name"
    EMAIL = "email"
    EMPLOYEE_ID = "employee_id"


@dataclass(frozen=True)
class BoundingBox:
    left: float
    top: float
    right: float
    bottom: float


@dataclass(frozen=True)
class TextElement:
    page_number: int
    text: str
    bounds: BoundingBox


@dataclass(frozen=True)
class DetectedPii:
    pii_type: PiiType
    value: str
    page_number: int
    bounds: BoundingBox
    protected: bool = False
    word_bounds: tuple[BoundingBox, ...] = ()


@dataclass
class FileAudit:
    path: str
    status: str = "pending"
    pages: int = 0
    detections: dict[str, int] = field(default_factory=dict)
    highlights: int = 0
    error: str | None = None


@dataclass
class AuditReport:
    files: list[FileAudit] = field(default_factory=list)
    verification: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SourcePage:
    source_path: Path
    source_page_number: int
    merged_page_number: int


@dataclass(frozen=True)
class Highlight:
    pii: DetectedPii
    source_path: Path


@dataclass(frozen=True)
class ProcessingConfig:
    input_folder: Path
    output_folder: Path
    protected_persons: tuple[str, ...]
    pii_types: tuple[PiiType, ...]
    employee_id_patterns: tuple[str, ...]
    highlight_color: tuple[float, float, float]
    highlight_opacity: float
    concurrency: int
    retry_count: int
    continue_on_error: bool
    ocr_enabled: bool
    protected_emails: tuple[str, ...] = ()
    gemini_chunk_words: int = 400
