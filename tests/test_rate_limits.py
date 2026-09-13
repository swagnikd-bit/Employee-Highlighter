import json
from types import SimpleNamespace

from pdf_redactor.identification.detector import GeminiDetector
from test_identification import words


def test_paces_calls_and_caches_duplicate_chunks(monkeypatch):
    now = [0.0]
    sleeps = []
    monkeypatch.setenv("GEMINI_REQUESTS_PER_MINUTE", "5")
    monkeypatch.setattr("pdf_redactor.identification.detector.time.monotonic", lambda: now[0])
    def sleep(delay):
        sleeps.append(delay)
        now[0] += delay
    monkeypatch.setattr("pdf_redactor.identification.detector.time.sleep", sleep)
    calls = []
    def generate(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(text=json.dumps({"entities": []}))
    detector = GeminiDetector("test", 0, SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    detector.identify(words("Alice Smith"), [])
    detector.identify(words("Bob Jones"), [])
    detector.identify(words("Alice Smith", 2), [])
    assert len(calls) == 2
    assert sleeps == [12.2]


def test_429_uses_server_retry_delay(monkeypatch):
    now = [0.0]
    sleeps = []
    monkeypatch.setattr("pdf_redactor.identification.detector.time.monotonic", lambda: now[0])
    def sleep(delay):
        sleeps.append(delay)
        now[0] += delay
    monkeypatch.setattr("pdf_redactor.identification.detector.time.sleep", sleep)
    class Limited(Exception):
        code = 429
        response_json = {"error": {"details": [{"retryDelay": "75s"}]}}
    attempts = []
    def generate(**kwargs):
        attempts.append(kwargs)
        if len(attempts) == 1:
            raise Limited()
        return SimpleNamespace(text='{"entities": []}')
    detector = GeminiDetector("test", 1, SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    detector.identify(words("Alice Smith"), [])
    assert sleeps == [75]
