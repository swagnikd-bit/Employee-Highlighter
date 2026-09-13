from pdf_redactor.adobe import merge


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
