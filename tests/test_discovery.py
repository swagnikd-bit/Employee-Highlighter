from pathlib import Path

from pdf_redactor.discovery import discover_pdfs


def test_discovery_is_case_insensitive_and_deterministic(tmp_path: Path) -> None:
    (tmp_path / "z-last.PDF").write_bytes(b"%PDF")
    (tmp_path / "A-first.pdf").write_bytes(b"%PDF")
    (tmp_path / "ignore.txt").write_text("not a pdf", encoding="utf-8")

    assert [path.name for path in discover_pdfs(tmp_path)] == ["A-first.pdf", "z-last.PDF"]
