from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import load_config
from .discovery import discover_pdfs
from .processing import run


LOGGER = logging.getLogger("pdf_redactor")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Merge PDFs and highlight detected PII.")
    parser.add_argument("--config", type=Path, required=True, help="Path to YAML configuration")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate configuration and list discovered PDFs without calling Adobe",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        pdfs = discover_pdfs(config.input_folder)
    except (OSError, ValueError) as exc:
        LOGGER.error("Validation failed: %s", exc)
        return 2

    LOGGER.info("Discovered %d PDF file(s)", len(pdfs))
    for pdf in pdfs:
        LOGGER.info("Queued: %s", pdf)
    if args.validate_only:
        return 0
    try:
        report = run(args.config)
    except (OSError, ValueError, RuntimeError) as exc:
        LOGGER.error("Processing failed: %s", exc)
        return 1
    required_checks = (
        "page_count_match",
        "page_dimensions_match",
        "protected_information_not_highlighted",
        "all_eligible_detections_highlighted",
    )
    if not all(report.verification.get(key, False) for key in required_checks):
        LOGGER.error("Verification failed: %s", report.verification)
        return 4
    LOGGER.info("Verification passed: %s", report.verification)
    return 0


if __name__ == "__main__":
    sys.exit(main())
