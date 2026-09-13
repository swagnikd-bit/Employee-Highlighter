import json
from types import SimpleNamespace

import pymupdf
import pytest
from pathlib import Path

from pdf_redactor.extraction.pymupdf import extract_words
from pdf_redactor.highlighting.pymupdf import add_highlights
from pdf_redactor.identification.detector import GeminiDetector, detect_pii


def test_only_directory_names_and_emails_get_word_quads():
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((50, 30), "Shared Security Governance Board")
        page.insert_text((50, 60), "Marcus")
        page.insert_text((50, 75), "Vance")
        page.insert_text((150, 60), "mvance@example.com")
        page.insert_text((300, 60), "Principal Cloud Security Architect")
        page.insert_text((50, 110), "Elena")
        page.insert_text((50, 125), "Rostova")
        page.insert_text((150, 110), "elena@example.com")
        page.insert_text((300, 110), "Lead DLP Specialist")
        payload = {"people": [
            {"names": ["Marcus Vance"], "emails": ["mvance@example.com"], "excluded_as": ""},
            {"names": ["Elena Rostova"], "emails": ["elena@example.com"], "excluded_as": "Elena Rostova"},
        ]}
        calls = []
        def generate(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(text=json.dumps(payload))
        client = SimpleNamespace(models=SimpleNamespace(generate_content=generate))
        detections = detect_pii(extract_words(pdf), ["Elena Rostova"], [], detector=GeminiDetector("test", 0, client))
        assert len(calls) == 1
        assert {item.value for item in detections} == {"Marcus Vance", "Elena Rostova", "mvance@example.com", "elena@example.com"}
        assert add_highlights(pdf, detections, (1, 1, 0), .35) == 2
        covered = []
        for annotation in page.annots():
            for index in range(0, len(annotation.vertices), 4):
                rectangle = pymupdf.Quad(annotation.vertices[index:index + 4]).rect
                covered.extend(word.text for word in extract_words(pdf)
                               if rectangle.contains(pymupdf.Point((word.bounds.left + word.bounds.right) / 2,
                                                                   (word.bounds.top + word.bounds.bottom) / 2)))
                assert rectangle.width < 150
        assert sorted(covered) == ["Marcus", "Vance", "mvance@example.com"]


def test_directory_rejects_name_that_spans_unrelated_table_cells():
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((50, 60), "Marcus")
        page.insert_text((300, 60), "Architect")
        payload = {"people": [{"names": ["Marcus Architect"], "emails": [], "excluded_as": ""}]}
        client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kwargs: SimpleNamespace(text=json.dumps(payload))))
        with pytest.raises(RuntimeError, match="not grounded in contiguous"):
            detect_pii(extract_words(pdf), [], [], detector=GeminiDetector("test", 0, client))


def test_daily_quota_stops_without_retry():
    class Exhausted(Exception):
        code = 429
        response_json = {"error": {"details": [{"violations": [{"quotaId": "GenerateRequestsPerDay"}]}]}}
    calls = []
    def generate(**kwargs):
        calls.append(kwargs)
        raise Exhausted()
    detector = GeminiDetector("test", 3, SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    with pytest.raises(RuntimeError, match="daily request quota exhausted"):
        detector.resolve_people([], [])
    assert len(calls) == 1


def test_input_roster_uses_precise_quads_with_simulated_directory():
    # Fixed service fixture checks geometry on the actual problematic input;
    # it does not stand in for a live identity-recognition result.
    directory = [
        ("Marcus Vance", "mvance@apex-defense.net"),
        ("Elena Rostova", "elena.rostova@apex-defense.net"),
        ("David Chen", "dchen@apex-defense.net"),
        ("Sarah Jenkins", "s.jenkins@apex-defense.net"),
        ("Tariq Al-Mansoor", "talmansoor@apex-defense.net"),
        ("Rachel Sterling", "rsterling@apex-defense.net"),
        ("Hiroshi Tanaka", "htanaka@partner-cloudsec.io"),
        ("Amara Okafor", "aokafor@apex-defense.net"),
        ("Lucas Alvarez", "lalvarez@partner-cloudsec.io"),
        ("Priya Sharma", "psharma@apex-defense.net"),
    ]
    payload = {"people": [{"names": [name], "emails": [email],
                           "excluded_as": "Elena Rostova" if name == "Elena Rostova" else ""}
                          for name, email in directory]}
    client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kwargs: SimpleNamespace(text=json.dumps(payload))))
    path = Path(__file__).resolve().parents[1] / "input" / "02_Cloud_Infrastructure_Topology.pdf"
    with pymupdf.open(path) as pdf:
        elements = extract_words(pdf)
        detections = detect_pii(elements, ["Elena Rostova"], [], detector=GeminiDetector("test", 0, client))
        table = [item for item in detections if item.page_number == 2]
        assert len(table) == 20
        assert sum(item.protected for item in table) == 2
        add_highlights(pdf, detections, (1, 1, 0), .35)
        page = pdf[1]
        assert len(list(page.annots())) == 18
        for annotation in page.annots():
            for index in range(0, len(annotation.vertices), 4):
                quad = pymupdf.Quad(annotation.vertices[index:index + 4]).rect
                assert quad.width < 180
                assert quad.height < 20
                for protected in table:
                    if protected.protected:
                        assert all(not quad.intersects(pymupdf.Rect(box.left, box.top, box.right, box.bottom))
                                   for box in protected.word_bounds)
