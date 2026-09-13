import inspect
from types import SimpleNamespace

from google.genai import types
from adobe.pdfservices.operation.pdf_services import PDFServices
from adobe.pdfservices.operation.pdfjobs.params.combine_pdf.combine_pdf_params import CombinePDFParams
from adobe.pdfservices.operation.pdfjobs.jobs.combine_pdf_job import CombinePDFJob

from pdf_redactor.adobe import merge
from pdf_redactor.identification.detector import SCHEMA


def test_gemini_sdk_accepts_schema():
    config = types.GenerateContentConfig(response_mime_type="application/json", response_json_schema=SCHEMA)
    assert config.response_json_schema == SCHEMA


def test_adobe_sdk_contract_and_download(tmp_path, monkeypatch):
    assert "input_stream" in inspect.signature(PDFServices.upload).parameters
    assert "combine_pdf_params" in inspect.signature(CombinePDFJob).parameters
    assert callable(CombinePDFParams().add_asset)
    assets = []
    class Service:
        def __init__(self, credentials):
            pass
        def upload(self, input_stream, mime_type):
            assets.append(input_stream)
            from adobe.pdfservices.operation.io.cloud_asset import CloudAsset
            return CloudAsset(asset_id="urn:aaid:AS:test")
        def submit(self, job):
            assert isinstance(job, CombinePDFJob)
            return "job-location"
        def get_job_result(self, location, result_type):
            assert location == "job-location"
            return SimpleNamespace(get_result=lambda: SimpleNamespace(get_asset=lambda: "result"))
        def get_content(self, asset):
            return SimpleNamespace(get_input_stream=lambda: b"merged-pdf")
    monkeypatch.setenv("PDF_SERVICES_CLIENT_ID", "test")
    monkeypatch.setenv("PDF_SERVICES_CLIENT_SECRET", "test")
    monkeypatch.setattr("adobe.pdfservices.operation.pdf_services.PDFServices", Service)
    paths = [tmp_path / "a.pdf", tmp_path / "b.pdf"]
    for path in paths:
        path.write_bytes(path.name.encode())
    target = tmp_path / "result.pdf"
    merge._combine(paths, target)
    assert assets == [b"a.pdf", b"b.pdf"]
    assert target.read_bytes() == b"merged-pdf"
