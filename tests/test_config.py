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


def test_dotenv_loads_values_without_overriding_terminal(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "terminal-key")
    (tmp_path / ".env").write_text("GEMINI_MODEL=custom-model\nGEMINI_API_KEY=file-key\n")
    config = tmp_path / "config.yaml"
    config.write_text("input_folder: input\noutput_folder: output\n")
    load_config(config)
    import os
    assert os.environ["GEMINI_MODEL"] == "custom-model"
    assert os.environ["GEMINI_API_KEY"] == "terminal-key"
    monkeypatch.delenv("GEMINI_MODEL")


def test_yaml_model_requires_migration(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("input_folder: input\noutput_folder: output\ngemini:\n  model: old-model\n")
    with pytest.raises(ValueError, match="GEMINI_MODEL"):
        load_config(config)
