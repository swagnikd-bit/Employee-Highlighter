from pathlib import Path

import pytest

from pdf_redactor.config import load_config


def test_load_config_resolves_values(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
input_folder: input
output_folder: output
protected_persons:
  - John Smith
processing:
  concurrency: 2
""",
        encoding="utf-8",
    )

    config = load_config(config_file)

    assert config.input_folder == Path("input")
    assert config.protected_persons == ("John Smith",)
    assert config.concurrency == 2


def test_invalid_opacity_is_rejected(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "input_folder: input\noutput_folder: output\nhighlight:\n  opacity: 2\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="highlight.opacity"):
        load_config(config_file)
