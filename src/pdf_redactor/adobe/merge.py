"""Adobe owns every combine operation; PyMuPDF is only used downstream."""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory


def validate_credentials() -> None:
    for key in ("PDF_SERVICES_CLIENT_ID", "PDF_SERVICES_CLIENT_SECRET"):
        if not os.environ.get(key):
            raise ValueError(f"Set {key} before processing PDFs")


def _combine(paths: list[Path], destination: Path) -> None:
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
    except Exception as exc:
        raise RuntimeError("Adobe PDF merge failed; check credentials, quota, PDF validity and connectivity") from exc
