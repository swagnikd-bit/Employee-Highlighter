import json
from types import SimpleNamespace

import pytest

from pdf_redactor.identification.detector import GeminiDetector, detect_pii
from pdf_redactor.models import BoundingBox, PiiType, TextElement


def words(text, page=1):
    return [TextElement(page, value, BoundingBox(i * 60, 10, i * 60 + 50, 20))
            for i, value in enumerate(text.split())]


class Detector:
    def identify(self, chunk, protected):
        return [dict(type="name", start=0, end=1, owner=""),
                dict(type="name", start=2, end=3, owner=""),
                dict(type="email", start=4, end=4, owner="Elena Rostova")]


def test_protected_names_and_email_ownership():
    result = detect_pii(words("Elena Rostova Alice Smith elena@example.com alice@example.com"),
                        ["Elena Rostova"], [], detector=Detector())
    assert {item.value: item.protected for item in result} == {
        "Elena Rostova": True, "Alice Smith": False,
        "elena@example.com": True, "alice@example.com": False,
    }


def test_exact_protection_without_model_detection_and_repeated_email():
    class Empty:
        def identify(self, chunk, protected):
            return []
    result = detect_pii(words("ELENA Rostova elena@example.com") + words("elena@example.com", 2),
                        ["Elena Rostova"], [], detector=Empty(), protected_emails=["elena@example.com"])
    assert len(result) == 3
    assert all(item.protected for item in result)


def test_gemini_rejects_invalid_word_ids():
    client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kwargs: SimpleNamespace(
        text=json.dumps({"entities": [{"type": "name", "start": 0, "end": 999, "owner": ""}]}))))
    detector = GeminiDetector("test", 0, client)
    with pytest.raises(RuntimeError, match="Gemini identification failed"):
        detector.identify(words("Alice Smith"), [])


def test_gemini_model_is_copied_from_environment(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "my-configured-model")
    detector = GeminiDetector(client=SimpleNamespace())
    assert detector.model == "my-configured-model"


def test_gemini_has_no_default_model(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    with pytest.raises(ValueError, match="GEMINI_MODEL"):
        GeminiDetector(client=SimpleNamespace())


def test_chunk_overlap_deduplicates_occurrences():
    class Repeating:
        def identify(self, chunk, protected):
            return [dict(type="name", start=i, end=i + 1, owner="")
                    for i in range(len(chunk) - 1) if chunk[i].text == "Alice"]
    text = " ".join(["context"] * 40 + ["Alice", "Smith"] + ["context"] * 40)
    result = detect_pii(words(text), [], [], detector=Repeating(), chunk_words=64)
    assert len(result) == 1
    assert result[0].pii_type == PiiType.NAME
