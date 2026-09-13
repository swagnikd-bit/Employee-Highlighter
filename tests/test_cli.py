from pdf_redactor import cli
from pdf_redactor.models import AuditReport


def test_prompt_replaces_exclusions_and_passes_to_pipeline(tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    config.write_text(f"input_folder: {tmp_path.as_posix()}\noutput_folder: output\nprotected_persons: [Old Person]\n")
    responses = iter(["Alice Smith; Bob Jones"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(responses))
    received = {}
    def run(path, **kwargs):
        received.update(kwargs)
        return AuditReport(verification={key: True for key in (
            "page_count_match", "page_dimensions_match", "protected_information_not_highlighted",
            "all_eligible_detections_highlighted")})
    monkeypatch.setattr(cli, "run", run)
    assert cli.main(["--config", str(config)]) == 0
    assert received == {"protected_persons": ("Alice Smith", "Bob Jones"),
                        "protected_emails": ()}


def test_prompt_requires_name_and_dash_clears(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    try:
        cli._prompt_exclusions("Names", ("Alice Smith",))
    except ValueError as exc:
        assert str(exc) == "Enter a full name, for example: Elena Rostova, or '-' to clear exclusions"
    else:
        raise AssertionError("Blank input should require an explicit exclusion name")
    monkeypatch.setattr("builtins.input", lambda prompt: "-")
    assert cli._prompt_exclusions("Names", ("Alice Smith",)) == ()


def test_validation_does_not_prompt(tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    config.write_text(f"input_folder: {tmp_path.as_posix()}\noutput_folder: output\n")
    def unexpected(prompt):
        raise AssertionError("Validation should not ask for exclusions")
    monkeypatch.setattr("builtins.input", unexpected)
    assert cli.main(["--config", str(config), "--validate-only"]) == 0
