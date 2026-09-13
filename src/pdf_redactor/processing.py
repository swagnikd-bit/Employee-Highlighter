from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pymupdf

from .config import load_config
from .adobe.merge import merge_pdfs, validate_credentials
from .discovery import discover_pdfs
from .extraction.pymupdf import extract_words
from .highlighting.pymupdf import add_highlights
from .identification.detector import GeminiDetector, detect_pii
from .models import AuditReport, FileAudit, SourcePage

LOGGER = logging.getLogger("pdf_redactor")


def _source_pages(paths: list[Path]) -> list[SourcePage]:
    source_pages: list[SourcePage] = []
    for path in paths:
        with pymupdf.open(path) as source:
            if source.needs_pass:
                raise ValueError(f"Password-protected PDF is not supported: {path.name}")
            first_merged_page = len(source_pages) + 1
            source_pages.extend(
                SourcePage(path, page_number, first_merged_page + page_number - 1)
                for page_number in range(1, len(source) + 1)
            )
    return source_pages


def _verify(
    source_pages: list[SourcePage],
    original: pymupdf.Document,
    highlighted: pymupdf.Document,
    detections,
    highlights: int,
) -> dict[str, object]:
    dimensions_match = all(original[index].rect == highlighted[index].rect for index in range(len(original)))
    eligible_count = sum(not detection.protected for detection in detections)
    protected_count = sum(detection.protected for detection in detections)
    return {
        "source_page_count": len(source_pages),
        "original_page_count": len(original),
        "highlighted_page_count": len(highlighted),
        "page_count_match": len(original) == len(highlighted) == len(source_pages),
        "page_order_preserved": [
            (item.source_path.name, item.source_page_number, item.merged_page_number)
            for item in source_pages
        ],
        "page_dimensions_match": dimensions_match,
        "protected_detections": protected_count,
        "protected_information_not_highlighted": all(
            not pymupdf.Rect(box.left, box.top, box.right, box.bottom).intersects(pymupdf.Quad(annotation.vertices[index:index + 4]).rect)
            for detection in detections if detection.protected
            for box in (detection.word_bounds or (detection.bounds,))
            for annotation in highlighted[detection.page_number - 1].annots() or []
            if annotation.type[0] == pymupdf.PDF_ANNOT_HIGHLIGHT
            for index in range(0, len(annotation.vertices or []), 4)
        ),
        "eligible_detections": eligible_count,
        "highlights_added": highlights,
        "all_eligible_detections_highlighted": eligible_count == highlights,
    }


def run(
    config_path: Path, *, protected_persons: tuple[str, ...] | None = None,
    protected_emails: tuple[str, ...] | None = None,
) -> AuditReport:
    config = load_config(config_path)
    if protected_persons is not None:
        config = replace(config, protected_persons=protected_persons)
    if protected_emails is not None:
        config = replace(config, protected_emails=protected_emails)
    paths = discover_pdfs(config.input_folder)
    if not paths:
        raise ValueError(f"No PDF files found in {config.input_folder}")

    config.output_folder.mkdir(parents=True, exist_ok=True)
    validate_credentials()
    source_pages = _source_pages(paths)
    detector = GeminiDetector(retry_count=config.retry_count)
    original_path = config.output_folder / "merged_original.pdf"
    highlighted_path = config.output_folder / "merged_highlighted.pdf"
    try:
        merge_pdfs(paths, original_path)
        with pymupdf.open(original_path) as merged:
            if len(merged) != len(source_pages):
                raise RuntimeError("Adobe merge returned an unexpected page count")
            elements = extract_words(merged)
            searchable_pages = {element.page_number for element in elements}
            missing = sorted(set(range(1, len(merged) + 1)) - searchable_pages)
            if missing:
                raise ValueError(f"Pages without searchable text: {missing}. OCR them before processing.")
            detections = detect_pii(
                elements, config.protected_persons, config.employee_id_patterns, config.pii_types,
                detector=detector, protected_emails=config.protected_emails,
                chunk_words=config.gemini_chunk_words,
            )
            highlights = add_highlights(merged, detections, config.highlight_color, config.highlight_opacity)
            merged.save(highlighted_path)
    finally:
        detector.close()

    original_snapshot = pymupdf.open(original_path)
    highlighted_snapshot = pymupdf.open(highlighted_path)
    report = AuditReport()
    for path in paths:
        page_numbers = {item.merged_page_number for item in source_pages if item.source_path == path}
        file_detections = [item for item in detections if item.page_number in page_numbers]
        counts = Counter(item.pii_type.value for item in file_detections)
        report.files.append(
            FileAudit(
                path=str(path),
                status="processed",
                pages=len(page_numbers),
                detections=dict(counts),
                highlights=sum(not item.protected for item in file_detections),
            )
        )
    report.verification = _verify(source_pages, original_snapshot, highlighted_snapshot, detections, highlights)
    report_path = config.output_folder / "audit.json"
    report_path.write_text(
        json.dumps(
            {"files": [file_audit.__dict__ for file_audit in report.files], "verification": report.verification},
            indent=2,
        ),
        encoding="utf-8",
    )
    original_snapshot.close()
    highlighted_snapshot.close()
    LOGGER.info("Created %s", original_path)
    LOGGER.info("Created %s", highlighted_path)
    LOGGER.info("Created %s", report_path)
    return report
