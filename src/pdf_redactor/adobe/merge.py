"""Adobe owns every combine operation; PyMuPDF is only used downstream."""
from __future__ import annotations

import os
import shutil
import time
from urllib.parse import urlparse
from pathlib import Path
from tempfile import TemporaryDirectory


def validate_credentials() -> None:
    keys = ["PDF_SERVICES_CLIENT_ID"]
    if not os.environ.get("PDF_SERVICES_ACCESS_TOKEN", "").strip():
        keys.append("PDF_SERVICES_CLIENT_SECRET")
    for key in keys:
        if not os.environ.get(key):
            raise ValueError(f"Set {key} before processing PDFs")


def _combine_with_token(paths: list[Path], destination: Path) -> None:
    import httpx

    base = "https://pdf-services.adobe.io"
    headers = {"Authorization": "Bearer " + os.environ["PDF_SERVICES_ACCESS_TOKEN"].strip(),
               "x-api-key": os.environ["PDF_SERVICES_CLIENT_ID"].strip()}
    stage = "asset creation"
    try:
        # Apply credentials only to Adobe API calls, never pre-signed storage URLs.
        with httpx.Client(timeout=120) as client:
            inputs = []
            for path in paths:
                stage = "asset creation"
                response = client.post(base + "/assets", headers=headers, json={"mediaType": "application/pdf"})
                response.raise_for_status()
                asset = response.json()
                stage = "asset upload"
                response = client.put(asset["uploadUri"], content=path.read_bytes(), headers={"Content-Type": "application/pdf"})
                response.raise_for_status()
                inputs.append({"assetID": asset["assetID"]})
            stage = "combine submission"
            response = client.post(base + "/operation/combinepdf", headers=headers, json={"assets": inputs})
            response.raise_for_status()
            location = response.headers["location"]
            parsed = urlparse(location)
            if parsed.scheme != "https" or parsed.hostname not in ("pdf-services.adobe.io", "pdf-services-ue1.adobe.io", "pdf-services-ew1.adobe.io"):
                raise RuntimeError("Adobe returned an unexpected job status URL")
            deadline = time.monotonic() + 600
            stage = "combine polling"
            while time.monotonic() < deadline:
                response = client.get(location, headers=headers)
                response.raise_for_status()
                result = response.json()
                if result["status"] == "done":
                    stage = "result download"
                    response = client.get(result["asset"]["downloadUri"])
                    response.raise_for_status()
                    destination.write_bytes(response.content)
                    return
                if result["status"] == "failed":
                    code = result.get("error", {}).get("code", "unknown")
                    raise RuntimeError(f"Adobe combine job failed (code {code})")
                time.sleep(3)
            raise RuntimeError("Adobe combine polling timed out after 10 minutes")
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        hint = "; replace the expired/invalid access token" if status == 401 else ""
        raise RuntimeError(f"Adobe {stage} failed (HTTP {status}){hint}") from exc


def _combine(paths: list[Path], destination: Path) -> None:
    if os.environ.get("PDF_SERVICES_ACCESS_TOKEN", "").strip():
        return _combine_with_token(paths, destination)
    from adobe.pdfservices.operation.auth.service_principal_credentials import ServicePrincipalCredentials
    from adobe.pdfservices.operation.pdf_services import PDFServices
    from adobe.pdfservices.operation.pdf_services_media_type import PDFServicesMediaType
    from adobe.pdfservices.operation.pdfjobs.jobs.combine_pdf_job import CombinePDFJob
    from adobe.pdfservices.operation.pdfjobs.params.combine_pdf.combine_pdf_params import CombinePDFParams
    from adobe.pdfservices.operation.pdfjobs.result.combine_pdf_result import CombinePDFResult

    service = PDFServices(credentials=ServicePrincipalCredentials(
        client_id=os.environ["PDF_SERVICES_CLIENT_ID"],
        client_secret=os.environ["PDF_SERVICES_CLIENT_SECRET"],
    ))
    params = CombinePDFParams()
    for path in paths:
        asset = service.upload(input_stream=path.read_bytes(), mime_type=PDFServicesMediaType.PDF)
        params.add_asset(asset)
    location = service.submit(CombinePDFJob(combine_pdf_params=params))
    asset = service.get_job_result(location, CombinePDFResult).get_result().get_asset()
    destination.write_bytes(service.get_content(asset).get_input_stream())


def merge_pdfs(paths: list[Path], destination: Path) -> None:
    if not paths:
        raise ValueError("No PDFs to merge")
    validate_credentials()
    try:
        with TemporaryDirectory(prefix="adobe-merge-") as directory:
            current = list(paths)
            level = 0
            while len(current) > 1:
                following = []
                for offset in range(0, len(current), 20):
                    batch = current[offset:offset + 20]
                    if len(batch) == 1:
                        following.append(batch[0])
                        continue
                    target = Path(directory) / f"{level}-{offset}.pdf"
                    _combine(batch, target)
                    following.append(target)
                current = following
                level += 1
            shutil.copyfile(current[0], destination)
    except ImportError as exc:
        raise RuntimeError("Install pdfservices-sdk: python -m pip install -e .") from exc
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError("Adobe PDF merge failed; check credentials, quota, PDF validity and connectivity") from exc
