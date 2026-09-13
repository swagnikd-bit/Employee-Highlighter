from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import PiiType, ProcessingConfig


def _required(mapping: dict[str, Any], key: str) -> Any:
    if key not in mapping:
        raise ValueError(f"Missing required configuration key: {key}")
    return mapping[key]


def load_config(path: Path) -> ProcessingConfig:
    with path.open("r", encoding="utf-8") as stream:
        raw = yaml.safe_load(stream) or {}

    processing = raw.get("processing", {})
    highlight = raw.get("highlight", {})
    color = tuple(float(value) for value in highlight.get("color", [1.0, 1.0, 0.0]))
    if len(color) != 3 or any(value < 0 or value > 1 for value in color):
        raise ValueError("highlight.color must contain three values between 0 and 1")

    config = ProcessingConfig(
        input_folder=Path(_required(raw, "input_folder")),
        output_folder=Path(_required(raw, "output_folder")),
        protected_persons=tuple(str(value) for value in raw.get("protected_persons", [])),
        pii_types=tuple(PiiType(value) for value in raw.get("pii_types", [PiiType.NAME.value])),
        employee_id_patterns=tuple(str(value) for value in raw.get("employee_id_patterns", [])),
        highlight_color=color,
        highlight_opacity=float(highlight.get("opacity", 0.35)),
        concurrency=int(processing.get("concurrency", 1)),
        retry_count=int(processing.get("retry_count", 3)),
        continue_on_error=bool(processing.get("continue_on_error", True)),
        ocr_enabled=bool(processing.get("ocr_enabled", True)),
    )
    if config.concurrency < 1:
        raise ValueError("processing.concurrency must be at least 1")
    if not 0 < config.highlight_opacity <= 1:
        raise ValueError("highlight.opacity must be greater than 0 and at most 1")
    return config
