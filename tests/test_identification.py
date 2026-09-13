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


def test_llm_resolves_excluded_email_and_alias_from_name_only():
    calls = []
    def generate(**kwargs):
        calls.append(json.loads(kwargs["contents"]))
        if "document_words" in calls[-1]:
            return SimpleNamespace(text=json.dumps({"people": [
                {"names": ["E. Rostova"], "emails": ["elena@example.com"], "excluded_as": "Elena Rostova"},
                {"names": ["Alice Smith"], "emails": ["alice@example.com"], "excluded_as": ""},
            ]}))
        chunk = calls[-1]["words"]
        entities = []
        for i, word in enumerate(chunk):
            if word["text"] in ("E.", "Alice"):
                entities.append(dict(type="name", start=i, end=i + 1, owner=""))
        return SimpleNamespace(text=json.dumps({"entities": entities}))
    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate))
    detector = GeminiDetector("test", 0, client)
    result = detect_pii(words("E. Rostova elena@example.com Alice Smith alice@example.com")
                        + words("elena@example.com", 2), ["Elena Rostova"], [], detector=detector)
    assert calls[0]["excluded_person_names"] == ["Elena Rostova"]
    assert "excluded_emails" not in calls[0]
    assert all(item.protected for item in result if item.value in ("E. Rostova", "elena@example.com"))
    assert all(not item.protected for item in result if item.value in ("Alice Smith", "alice@example.com"))


def test_resolved_email_must_be_present_in_document():
    client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kwargs: SimpleNamespace(
        text=json.dumps({"names": [], "emails": ["invented@example.com"]}))))
    with pytest.raises(RuntimeError, match="email absent from the document"):
        GeminiDetector("test", 0, client).resolve_identity(words("Elena Rostova"), ["Elena Rostova"])


def test_llm_owner_protects_name_variant():
    class Variant:
        def identify(self, chunk, protected):
            return [dict(type="name", start=0, end=1, owner="Elena Rostova")]
    result = detect_pii(words("E. Rostova"), ["Elena Rostova"], [], detector=Variant())
    assert len(result) == 1 and result[0].protected


def test_wrapped_email_is_grounded_and_protected_on_both_lines():
    elements = [TextElement(1, "elena@apex-", BoundingBox(100, 10, 180, 20)),
                TextElement(1, "defense.net", BoundingBox(100, 22, 170, 32))]
    client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kwargs: SimpleNamespace(
        text=json.dumps({"people": [{"names": [], "emails": ["elena@apex-defense.net"], "excluded_as": "Elena Rostova"}]}
                        if "document_words" in json.loads(kwargs["contents"]) else {"entities": []}))))
    result = detect_pii(elements, ["Elena Rostova"], [], detector=GeminiDetector("test", 0, client))
    assert len(result) == 1
    assert len(result[0].word_bounds) == 2
    assert all(item.protected and item.value == "elena@apex-defense.net" for item in result)
