from pdf_redactor.adobe import merge
import httpx
import pytest


def test_adobe_batches_preserve_order(tmp_path, monkeypatch):
    monkeypatch.setenv("PDF_SERVICES_CLIENT_ID", "test")
    monkeypatch.setenv("PDF_SERVICES_CLIENT_SECRET", "test")
    calls = []
    def combine(paths, destination):
        calls.append(len(paths))
        destination.write_bytes(b"".join(path.read_bytes() for path in paths))
    monkeypatch.setattr(merge, "_combine", combine)
    paths = []
    for i in range(43):
        path = tmp_path / f"{i}.pdf"
        path.write_bytes(f"{i},".encode())
        paths.append(path)
    target = tmp_path / "result.pdf"
    merge.merge_pdfs(paths, target)
    assert calls == [20, 20, 3, 3]
    assert target.read_bytes() == b"".join(path.read_bytes() for path in paths)


def test_token_merge_keeps_credentials_off_storage_requests(tmp_path, monkeypatch):
    monkeypatch.setenv("PDF_SERVICES_CLIENT_ID", "test-id")
    monkeypatch.setenv("PDF_SERVICES_ACCESS_TOKEN", "test-token")
    requests = []
    def handle(request):
        requests.append(request)
        if request.url.path == "/assets":
            return httpx.Response(200, json={"assetID": "asset", "uploadUri": "https://storage.example/upload"})
        if request.url.path == "/operation/combinepdf":
            import json
            assert json.loads(request.content) == {"assets": [{"assetID": "asset"}, {"assetID": "asset"}]}
            return httpx.Response(201, headers={"location": "https://pdf-services.adobe.io/status"})
        if request.url.path == "/status":
            return httpx.Response(200, json={"status": "done", "asset": {"downloadUri": "https://storage.example/download"}})
        return httpx.Response(200, content=b"merged")
    original_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original_client(transport=httpx.MockTransport(handle), **kwargs))
    paths = [tmp_path / "a.pdf", tmp_path / "b.pdf"]
    for path in paths:
        path.write_bytes(b"pdf")
    target = tmp_path / "merged.pdf"
    merge.merge_pdfs(paths, target)
    assert target.read_bytes() == b"merged"
    for request in requests:
        if request.url.host == "storage.example":
            assert "authorization" not in request.headers
            assert "x-api-key" not in request.headers
        else:
            assert request.headers["authorization"] == "Bearer test-token"


def test_token_expiry_reports_status_without_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("PDF_SERVICES_CLIENT_ID", "test-id")
    monkeypatch.setenv("PDF_SERVICES_ACCESS_TOKEN", "test-secret-token")
    original_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original_client(
        transport=httpx.MockTransport(lambda request: httpx.Response(401)), **kwargs))
    path = tmp_path / "a.pdf"
    path.write_bytes(b"pdf")
    with pytest.raises(RuntimeError, match="HTTP 401") as error:
        merge._combine_with_token([path, path], tmp_path / "result.pdf")
    assert "test-secret-token" not in str(error.value)
