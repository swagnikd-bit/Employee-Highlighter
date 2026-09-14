# Environment Setup Guide

This guide creates a repeatable local environment for Employee PDF Highlighter on Windows with PowerShell. The application requires Python 3.11 or newer, a Gemini API key, and Adobe PDF Services credentials.

## Prerequisites

Install the following before starting:

- Python 3.11 or newer, with the `py` launcher available in PowerShell.
- Internet access to Google Gemini and Adobe PDF Services.
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey).
- An Adobe PDF Services project and credentials from [Adobe's getting-started guide](https://developer.adobe.com/document-services/docs/overview/pdf-services-api/gettingstarted).

Confirm Python:

```powershell
py --version
```

## One-time setup

Run every command from the repository root, the folder containing `pyproject.toml`:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
Copy-Item .env.example .env
Copy-Item config.example.yaml config.yaml
New-Item -ItemType Directory -Force input, output | Out-Null
```

The editable install registers the `pdf-redactor` command and makes local source changes immediately available. `requirements.txt` includes both runtime packages and `pytest`, so the same environment can run the application and its test suite.

If PowerShell blocks activation for the current user, run this once in an elevated or permitted PowerShell session, then repeat activation:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Activation is optional. Without it, replace `python` with `.\.venv\Scripts\python.exe` and `pdf-redactor` with `.\.venv\Scripts\pdf-redactor.exe`.

## Configure credentials

Open `.env` and replace the empty values:

```dotenv
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL=your-exact-model-id
GEMINI_REQUESTS_PER_MINUTE=5
PDF_SERVICES_CLIENT_ID=your-adobe-client-id
PDF_SERVICES_ACCESS_TOKEN=
PDF_SERVICES_CLIENT_SECRET=your-adobe-client-secret
```

Use an exact Gemini model ID that is available to the key and supports structured JSON output. The application deliberately has no model fallback.

Configure Adobe using one authentication mode:

- SDK-managed mode: set `PDF_SERVICES_CLIENT_ID` and `PDF_SERVICES_CLIENT_SECRET`; leave `PDF_SERVICES_ACCESS_TOKEN` empty.
- Access-token mode: set `PDF_SERVICES_CLIENT_ID` and `PDF_SERVICES_ACCESS_TOKEN`; the access token takes precedence over the secret.

Do not commit `.env`, paste credentials into YAML, or place credentials in documentation. The repository's `.gitignore` is expected to exclude `.env` and generated output.

## Configure processing

Edit `config.yaml` as needed. The copied example is a valid starting point:

```yaml
input_folder: ./input
output_folder: ./output
protected_persons:
  - Elena Rostova
protected_emails: []
pii_types:
  - name
  - email
gemini:
  chunk_words: 400
highlight:
  color: [1.0, 1.0, 0.0]
  opacity: 0.35
processing:
  concurrency: 1
  retry_count: 3
  continue_on_error: false
  ocr_enabled: false
```

Paths are relative to the current working directory. Input discovery is nonrecursive and only considers PDFs directly inside `input/`. Keep `output/` separate from `input/` so generated PDFs are never rediscovered as source files. OCR is not implemented; use searchable PDFs and keep `ocr_enabled` set to `false`.

## Verify the environment

Put at least one searchable PDF directly in `input/`, then run configuration validation. This checks YAML and lists discovered files without calling Adobe or Gemini:

```powershell
pdf-redactor --config config.yaml --validate-only
```

Run the automated test suite:

```powershell
python -m pytest
```

## Run a first processing job

Interactive mode asks for the names to protect before any service request:

```powershell
pdf-redactor --config config.yaml
```

For scheduled or CI-style execution, use the exclusions already present in `config.yaml` and suppress the prompt:

```powershell
pdf-redactor --config config.yaml --no-prompt
```

Successful processing writes the following files to `output/`:

- `merged_original.pdf`: merged source content before new highlights.
- `merged_highlighted.pdf`: the merged PDF with removable yellow annotations.
- `audit.json`: per-file detection counts and verification results.

A successful command returns exit code `0`. Configuration or discovery failures return `2`, processing failures return `1`, and failed output verification returns `4`.

## PowerShell session without `.env`

For temporary environments, variables can be supplied directly in the same terminal session:

```powershell
$env:GEMINI_API_KEY = "your-gemini-api-key"
$env:GEMINI_MODEL = "your-exact-model-id"
$env:PDF_SERVICES_CLIENT_ID = "your-adobe-client-id"
$env:PDF_SERVICES_CLIENT_SECRET = "your-adobe-client-secret"
pdf-redactor --config config.yaml --no-prompt
```

Environment variables already present in the terminal take precedence over values in `.env`, including empty values. Remove a stale override with `Remove-Item Env:NAME` before retrying.

## Troubleshooting

| Message or symptom | Resolution |
| --- | --- |
| `Set GEMINI_MODEL...` | Set the exact model ID in `.env` and run from the repository root. |
| `Set GEMINI_API_KEY...` | Fill `GEMINI_API_KEY`; verify the terminal has no empty override. |
| `Set PDF_SERVICES_CLIENT_ID...` | Set the Adobe client ID. |
| Adobe client secret error | Set a matching client secret, or clear it and provide a valid access token. |
| `No PDFs found` or empty discovery | Put `.pdf` files directly in `input/`; nested folders are ignored. |
| `OCR is not implemented` | Supply searchable PDFs and set `processing.ocr_enabled: false`. |
| `No module named ...` | Activate `.venv` and rerun `python -m pip install -r requirements.txt` followed by `python -m pip install -e .`. |
| Access token returns HTTP 401 | Replace the expired token, or clear it and use SDK-managed client-secret authentication. |

For service failures, preserve the terminal error, `audit.json` when present, and the input file list. Do not include `.env` or secret-bearing logs when sharing diagnostics.