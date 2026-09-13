import pymupdf
import pytest

from pdf_redactor import processing


@pytest.mark.parametrize("override", [False, True])
def test_pipeline_with_simulated_services(tmp_path, monkeypatch, override):
    folder = tmp_path / "input"
    folder.mkdir()
    for name, text in [("a.pdf", "Elena Rostova elena@example.com"), ("b.pdf", "Alice Smith alice@example.com")]:
        with pymupdf.open() as pdf:
            pdf.new_page().insert_text((50, 50), text)
            pdf.save(folder / name)
    def merge(paths, target):
        with pymupdf.open() as pdf:
            for path in paths:
                with pymupdf.open(path) as source:
                    pdf.insert_pdf(source)
            pdf.save(target)
    class Detector:
        def __init__(self, *args, **kwargs):
            pass
        def close(self):
            pass
        def identify(self, words, protected):
            return [dict(type="name", start=0, end=1, owner="")]
    monkeypatch.setattr(processing, "validate_credentials", lambda: None)
    monkeypatch.setattr(processing, "merge_pdfs", merge)
    monkeypatch.setattr(processing, "GeminiDetector", Detector)
    config = tmp_path / "config.yaml"
    config.write_text(f'input_folder: {folder.as_posix()}\noutput_folder: {(tmp_path / "output").as_posix()}\n'
                      'protected_persons: [Elena Rostova]\nprotected_emails: [elena@example.com]\n')
    report = processing.run(config, **({"protected_persons": ("Alice Smith",),
                                        "protected_emails": ("alice@example.com",)} if override else {}))
    assert report.verification["page_count_match"]
    assert report.verification["protected_information_not_highlighted"]
    assert report.verification["highlights_added"] == 2
    with pymupdf.open(tmp_path / "output" / "merged_highlighted.pdf") as pdf:
        assert len(list(pdf[0].annots() or [])) == (2 if override else 0)
        assert len(list(pdf[1].annots() or [])) == (0 if override else 2)
