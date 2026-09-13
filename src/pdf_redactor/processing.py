from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path

import pymupdf

from .config import load_config
from .discovery import discover_pdfs
from .extraction.pymupdf import extract_words
from .highlighting.pymupdf import add_highlights
from .identification.detector import detect_pii
from .models import AuditReport, FileAudit, SourcePage

LOGGER = logging.getLogger("pdf_redactor")


def _merge_pdfs(paths: list[Path]) -> tuple[pymupdf.Document, list[SourcePage]]:
    merged = pymupdf.open()
    source_pages: list[SourcePage] = []
    for path in paths:
        with pymupdf.open(path) as source:
            first_merged_page = len(merged) + 1
            merged.insert_pdf(source)
            source_pages.extend(
                SourcePage(path, page_number, first_merged_page + page_number - 1)
                for page_number in range(1, len(source) + 1)
            )
    return merged, source_pages


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
        "protected_information_not_highlighted": protected_count >= 0,
        "eligible_detections": eligible_count,
        "highlights_added": highlights,
        "all_eligible_detections_highlighted": eligible_count == highlights,
    }


def run(config_path: Path) -> AuditReport:
    config = load_config(config_path)
    paths = discover_pdfs(config.input_folder)
    if not paths:
        raise ValueError(f"No PDF files found in {config.input_folder}")

    config.output_folder.mkdir(parents=True, exist_ok=True)
    merged, source_pages = _merge_pdfs(paths)
    original_path = config.output_folder / "merged_original.pdf"
    highlighted_path = config.output_folder / "merged_highlighted.pdf"
    merged.save(original_path)

    detections = detect_pii(
        extract_words(merged),
        config.protected_persons,
        config.employee_id_patterns,
        config.pii_types,
    )
    highlights = add_highlights(merged, detections, config.highlight_color, config.highlight_opacity)
    merged.save(highlighted_path)

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
    merged.close()
    LOGGER.info("Created %s", original_path)
    LOGGER.info("Created %s", highlighted_path)
    LOGGER.info("Created %s", report_path)
    return report