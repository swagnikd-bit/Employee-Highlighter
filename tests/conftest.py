import pytest


@pytest.fixture(autouse=True)
def isolate_service_environment(tmp_path, monkeypatch):
    # Never load developer credentials into tests or contact live services.
    monkeypatch.chdir(tmp_path)
    for name in ("GEMINI_API_KEY", "GEMINI_MODEL", "PDF_SERVICES_CLIENT_ID",
                 "PDF_SERVICES_ACCESS_TOKEN", "PDF_SERVICES_CLIENT_SECRET"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GEMINI_REQUESTS_PER_MINUTE", "10000")
