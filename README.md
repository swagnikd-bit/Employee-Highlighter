# Employee PDF Highlighter

Merge every PDF directly inside `input/`, preserve page content, and highlight human names and email addresses except those belonging to configured protected people. Names are identified by Gemini; there is no spaCy or local name heuristic. Adobe PDF Services performs PDF combination. PyMuPDF extracts word coordinates and adds yellow PDF annotations locally.

Highlights leave information readable and removable. This application does not redact or erase data.

## Contents

- [Setup guide](#setup-guide)
- [Usage guide](#usage-guide)
- [Architecture and file structure](#architecture)
- [Pipeline in detail](#pipeline-in-detail)
- [Audit report and failure behavior](#audit-report-and-failure-behavior)
- [Setup](#setup-powershell)
- [Environment configuration](#environment-configuration)
- [Configure and run](#configure-and-run)
- [Detection and protection rules](#how-detection-and-protection-work)
- [Migrating and troubleshooting](#migrating-and-troubleshooting)
- [Limits and data flow](#limits-and-data-flow)
- [Development](#development)

## Setup guide

For a complete Windows/PowerShell installation, credential configuration, validation, first run, and troubleshooting walkthrough, see [SETUP.md](SETUP.md). The one-command dependency source is [requirements.txt](requirements.txt).

## Usage guide

For CLI commands, configuration semantics, protection behavior, processing stages, audit fields, exit codes, and operational limits, see [USAGE.md](USAGE.md).

## Architecture

This is a Python command-line application with a sequential pipeline. `processing.py` coordinates independent modules for discovery, merging, extraction, identification, highlighting, and reporting. Shared dataclasses in `models.py` carry configuration, page mappings, text coordinates, and detections between modules.

```mermaid
flowchart TD
    ENV[Environment variables and local .env] --> CONFIG[Load and validate configuration]
    YAML[config.yaml] --> CONFIG
    CLI[pdf-redactor CLI] --> CONFIG
    CONFIG --> DISCOVER[Discover and sort input PDFs]
    DISCOVER --> VALIDATE{Validate-only?}
    VALIDATE -->|Yes| LIST[List files and exit]
    VALIDATE -->|No| MAP[Check credentials and map source pages]
    MAP --> ADOBE[Adobe PDF Services: combine PDFs]
    ADOBE --> ORIGINAL[merged_original.pdf]
    ORIGINAL --> EXTRACT[PyMuPDF: extract words and coordinates]
    EXTRACT --> DETECT[Gemini: resolve excluded identity and detect occurrences]
    DETECT --> PROTECT[Local protection, email matching and deduplication]
    PROTECT --> ANNOTATE[PyMuPDF: add eligible highlights]
    ANNOTATE --> RESULT[merged_highlighted.pdf]
    RESULT --> VERIFY[Verify outputs and aggregate per-file counts]
    ORIGINAL --> VERIFY
    VERIFY --> AUDIT[audit.json and CLI exit status]
```

The single-input path copies the PDF to `merged_original.pdf` without an Adobe combine request. Gemini receives the full extracted text with page/position context once and returns a directory of people, observed name forms, email addresses and excluded identities. Local code matches those exact values to PDF words; Gemini does not control annotation rectangles. Adobe receives complete PDFs for combination. Neither provider draws the final highlights: the application uses the returned word references to annotate the downloaded PDF locally.

### Repository structure

```text
Employee-Highlighter/
|-- README.md                         # Setup, architecture and operating guide
|-- pyproject.toml                    # Dependencies, packaging and CLI entry point
|-- .gitignore                        # Ignore local secrets and generated artifacts
|-- .env.example                      # Empty service/model environment template
|-- .env                              # Your local values; create from the template
|-- config.example.yaml               # Example document-processing settings
|-- config.yaml                       # Your local settings; create from the example
|-- input/                            # Source PDFs; direct children only
|-- output/
|   |-- merged_original.pdf           # Combined PDF before new annotations
|   |-- merged_highlighted.pdf        # Combined PDF with eligible highlights
|   `-- audit.json                    # Per-file counts and verification results
|-- src/
|   `-- pdf_redactor/
|       |-- __init__.py
|       |-- cli.py                    # Argument parsing, logging and exit codes
|       |-- config.py                 # .env loading and YAML validation
|       |-- discovery.py              # Deterministic PDF discovery
|       |-- models.py                 # Shared dataclasses and PII enum
|       |-- processing.py             # Pipeline orchestration and audit writing
|       |-- adobe/
|       |   |-- __init__.py
|       |   `-- merge.py              # Adobe SDK uploads, combine jobs and batching
|       |-- extraction/
|       |   |-- __init__.py
|       |   `-- pymupdf.py            # Coordinate-aware word extraction
|       |-- identification/
|       |   |-- __init__.py
|       |   `-- detector.py           # Identity resolution, occurrence detection and protection
|       `-- highlighting/
|           |-- __init__.py
|           `-- pymupdf.py            # PDF highlight annotation creation
`-- tests/
    |-- test_config.py                # Settings, .env precedence and migration
    |-- test_discovery.py             # Filename filtering and ordering
    |-- test_adobe.py                 # Merge batching and order
    |-- test_identification.py        # Protection, model selection and span checks
    |-- test_processing.py            # Pipeline with generated PDFs/mock services
    `-- test_sdk_contracts.py         # Installed SDK request/download compatibility
```

`.env` and `config.yaml` are user-created files. `output/` contains runtime artifacts. Installed package metadata (`*.egg-info`) and Python caches (`__pycache__`) are generated files, not pipeline modules.

### Modules and interfaces

| Module | Main interface | Responsibility and result |
| --- | --- | --- |
| `cli.py` | `main(argv)` | Reads CLI arguments, logs queued files, prompts for exclusions unless disabled, runs processing and returns an exit code. |
| `config.py` | `load_config(path)` | Loads the current directory's `.env`, parses YAML and returns `ProcessingConfig`. Rejects invalid highlight/chunk/retry settings, enabled OCR and YAML model settings. |
| `discovery.py` | `discover_pdfs(input_folder)` | Returns a sorted list of direct-child PDF paths. Rejects a missing input folder or a path that is not a directory. |
| `processing.py` | `run(config_path, protected_persons=None, protected_emails=None)` | Applies optional runtime exclusions, coordinates services and local processing, saves the PDFs, builds an `AuditReport` and writes JSON. `_source_pages()` builds provenance; `_verify()` checks final outputs. |
| `adobe/merge.py` | `merge_pdfs(paths, destination)` | Combines ordered inputs using Adobe, or copies a single input. `_combine()` uploads assets, submits a job, retrieves its result and downloads bytes. |
| `extraction/pymupdf.py` | `extract_words(document)` | Returns `TextElement` objects from PDF words in native cell/block order, including merged page numbers and original word rectangles. |
| `identification/detector.py` | `GeminiDetector.resolve_people()` and `detect_pii()` | Requests a human-person directory, grounds returned values in PDF text, matches exact occurrences and applies exclusions. |
| `highlighting/pymupdf.py` | `add_highlights(document, detections, color, opacity)` | Skips protected detections, rejects conflicting overlaps, adds PDF annotations and returns the number added. |

### Data models and page numbering

| Model | Contents | Use |
| --- | --- | --- |
| `ProcessingConfig` | Folders, protected values, PII types, highlight options and processing settings | Carries validated YAML settings. Credentials and the Gemini model are read separately from the environment. |
| `SourcePage` | Source path, source page number, merged page number | Associates detections with their original file for the audit. |
| `BoundingBox` | `left`, `top`, `right`, `bottom` | Stores the rectangle used for annotation placement. |
| `TextElement` | Page number, word text and bounds | Connects extracted text to existing PDF page coordinates. |
| `DetectedPii` | PII type, value, page number, envelope bounds, precise `word_bounds` and `protected` flag | Defines one annotation candidate or protected rectangle. |
| `FileAudit` | Path, status, pages, detection counts, highlight count and error field | Represents one source file in the JSON report. |
| `AuditReport` | File audits and verification fields | Returned to the CLI and serialized to `audit.json`. |

Source and merged page numbers in these models are **1-based**. PyMuPDF page access is **0-based**, so annotation code subtracts one. The production directory flow uses exact text matching rather than model-generated word IDs. Each candidate carries the bounds of its actual PDF words; envelope bounds are retained for compatibility but do not control highlight placement when precise bounds are present. The `Highlight` dataclass also exists in `models.py`, but the current pipeline passes `DetectedPii` directly to the annotation module.

For example, merging a two-page `a.pdf` followed by a one-page `b.pdf` produces this mapping:

| Source file | Source page | Merged page |
| --- | --- | --- |
| `a.pdf` | 1 | 1 |
| `a.pdf` | 2 | 2 |
| `b.pdf` | 1 | 3 |

## Pipeline in detail

### 1. Startup and input discovery

The `pdf-redactor` command is registered in `pyproject.toml` as `pdf_redactor.cli:main`. The CLI loads configuration and logs the discovered files. In validation mode it exits at this point. For a processing run, `run()` loads configuration/discovery again, rejects an empty input list, creates the output folder, checks Adobe credential presence, inspects source page counts/password requirements and initializes the Gemini client from the environment. Credential presence checks do not establish whether credentials are valid remotely.

### 2. Adobe combination

With client-secret authentication, each combine operation constructs Adobe service-principal credentials, uploads PDFs as assets in source order, adds those assets to `CombinePDFParams`, submits `CombinePDFJob`, retrieves `CombinePDFResult` and downloads the resulting asset. With access-token authentication, the REST path creates assets, uploads to their pre-signed URLs, submits `/operation/combinepdf`, polls the returned Adobe status URL and downloads the result. Bearer tokens and client IDs are sent only to Adobe API endpoints, never to storage URLs. Polling stops after ten minutes; HTTP failures report the processing stage and status without printing credentials. Intermediate combined PDFs are stored in a temporary directory that is cleaned up when merging finishes or fails.

The batching loop groups at most 20 files per operation. With 43 inputs, the first round combines groups of 20, 20 and 3; the next round combines those three results. A group containing a single file is carried forward without an unnecessary combine call. The final result is copied to the configured original-output path. The pipeline checks the downloaded PDF's page count against the source page map before extraction.

### 3. One Gemini request for the people directory

PyMuPDF reads words in native cell/block order (`sort=False`) so wrapped names and emails remain adjacent. The pipeline rejects pages without searchable words.

`GeminiDetector.resolve_people()` submits the extracted corpus with page and word positions, plus only the user's excluded names. The model returns people and their observed names/email addresses, not arbitrary word ranges. The system instruction explicitly excludes headings, sentences, technical terms, departments, organizations, labels, job titles and security clearances from human names. It asks the model to determine identity and ownership from contact rows and document context, including name variants and wrapped addresses.

An illustrative response is:

```json
{
  "people": [
    {"names": ["Marcus Vance"], "emails": ["mvance@example.com"], "excluded_as": ""},
    {"names": ["Elena Rostova"], "emails": ["elena@example.com"], "excluded_as": "Elena Rostova"}
  ]
}
```

`excluded_as` must be empty or an exact user-supplied excluded name. Each returned name must match a contiguous occurrence in the actual PDF words. Each address must occur in the document, including validated reconstructed wrapped emails. Invented values or invalid structures stop processing. This request includes the full corpus; its size must fit the selected model's context window.

### 4. Exact matching and safe geometry

Local matching locates every occurrence of the directory's observed name forms. Case and surrounding punctuation are normalized, and hyphenated names can match wrapped fragments. Adjacent words must remain physically close on the same line or align on nearby wrapped lines. Matches cannot span unrelated distant table cells. There is no local NER or capitalization-based name discovery: Gemini decides which observed strings are human names.

Email syntax matching also covers model omissions. Only directory ownership/exclusion data or explicit unattended overrides decide protected email addresses; usernames alone do not establish ownership. Excluded name forms and addresses are protected across all pages.

Every detection stores individual word rectangles. Multiline names and addresses produce multiple highlight quads in one entity annotation, rather than a large enclosing rectangle. Duplicate occurrences with identical word geometry are consolidated. This prevents a wrapped name from painting unrelated content between its lines or across its table row.

### 5. Annotation and output verification

The annotation module opens the existing merged pages, skips protected candidates, checks each eligible word rectangle against protected word rectangles and adds highlight annotations with precise word quads, the configured color and opacity. It saves a separate highlighted PDF; it does not rebuild pages from extracted text. The Gemini client is closed after this processing stage, including when that stage fails.

The pipeline reopens both output PDFs, aggregates detections by source-page mapping, calculates verification fields and writes the audit. The CLI then requires the four Boolean verification checks below to pass before returning success.

## Audit report and failure behavior

`audit.json` has two top-level keys: `files` and `verification`. Each processed source entry includes its path, page count, detection counts by type and highlight count. Detection counts include protected candidates. Counts represent **entity occurrences**, not unique people. Repeated names count again. A multiline occurrence can have several word quads inside one annotation.

| Verification field | Meaning |
| --- | --- |
| `source_page_count`, `original_page_count`, `highlighted_page_count` | Page totals at each stage. |
| `page_count_match` | Both outputs and the source map have the same page count; required by the CLI. |
| `page_order_preserved` | The expected ordered list of source filename, source page and merged page triples. This is provenance data, not an independent content comparison that proves Adobe preserved order. |
| `page_dimensions_match` | Original and highlighted page rectangles match; required by the CLI. This compares the two outputs, not each source page to Adobe's result. |
| `protected_detections` | Number of protected rectangle candidates. |
| `protected_information_not_highlighted` | No highlight word quad in the highlighted output intersects a protected word rectangle; required by the CLI. Includes preexisting highlights. |
| `eligible_detections` | Number of unprotected rectangle candidates. |
| `highlights_added` | Number of annotations added during this run. |
| `all_eligible_detections_highlighted` | Eligible candidate count equals added annotation count; required by the CLI. It does not independently inspect every annotation or prove all real-world names were detected. |

Processing stops on an input or service failure; files are not silently skipped. Gemini retries malformed responses and service codes `429`, `500`, `502`, `503` and `504`, with additional attempts controlled by `retry_count`. Non-rate-limit backoff is capped at eight seconds; rate limits wait at least 61 seconds or a longer server retry delay. Other exceptions stop the request. Adobe jobs are not automatically resubmitted by the application's merge wrapper.

The audit is written only after annotation processing and output verification calculations complete. Earlier failures are logged to the terminal and do not produce a fresh failure audit, although `FileAudit` has an error field for future use. A Boolean verification failure still has an audit and returns exit code `4`. Outputs are written in stages rather than as an atomic set; retain the exit status and review timestamps when diagnosing an interrupted run.

## Setup (PowerShell)

Requires Python 3.11 or newer and internet access to both services.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
Copy-Item config.example.yaml config.yaml
Copy-Item .env.example .env
```

Create a Gemini API key in [Google AI Studio](https://aistudio.google.com/apikey). Create Adobe PDF Services credentials using [Adobe's getting-started guide](https://developer.adobe.com/document-services/docs/overview/pdf-services-api/gettingstarted).

## Environment configuration

Open `.env` and fill in the Gemini settings and one Adobe authentication option below. Copy the exact Gemini model ID from the model you intend to use with your API key; the application does not choose a model or supply a fallback.

```dotenv
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL=gemini-3.5-flash
GEMINI_REQUESTS_PER_MINUTE=5
PDF_SERVICES_CLIENT_ID=your-adobe-client-id
PDF_SERVICES_ACCESS_TOKEN=
PDF_SERVICES_CLIENT_SECRET=your-adobe-client-secret
```

The credential values above are placeholders; replace them before processing. `gemini-3.5-flash` is the model ID selected for this setup and stored only in the environment. Your key must have access to that model; live availability has not been validated.

| Variable | What to paste | Required for processing |
| --- | --- | --- |
| `GEMINI_API_KEY` | Your Gemini API key | Yes |
| `GEMINI_MODEL` | The exact model ID available to that key, supporting structured JSON output | Yes |
| `PDF_SERVICES_CLIENT_ID` | The client ID from your Adobe PDF Services credentials | Yes |
| `PDF_SERVICES_ACCESS_TOKEN` | Generated Adobe access token; takes precedence over the secret | Required if no secret |
| `PDF_SERVICES_CLIENT_SECRET` | Matching Adobe client secret; SDK obtains tokens automatically | Required if no access token |
| `GEMINI_REQUESTS_PER_MINUTE` | Local request pacing allowance; defaults to `5` | Optional |

Adobe combination uses PDF Services jobs and requires no AI model name. With `PDF_SERVICES_ACCESS_TOKEN` set, the merge module calls Adobe REST endpoints directly with the token and client ID. With no token, it uses the Adobe SDK and client ID/secret instead. Temporary tokens expire and are not refreshed automatically: replace the token, or clear it and configure a client secret for SDK-managed authentication. Paste the client ID once; do not duplicate it when copying. For Gemini, credentials and a model ID are separate settings: the key authenticates the request and `GEMINI_MODEL` selects the model. Change that environment value to change models; no Python or YAML edit is needed.

The application loads `.env` from the **current working directory**, not the directory of the YAML file. Run commands from the repository root when using the `.env` copied above. Existing terminal or deployment environment variables take precedence over `.env`, even if their values are empty. Remove a stale terminal variable if you want the file's value to apply. `.env` is ignored by Git; `.env.example` contains empty credential fields and nonsecret pacing settings and is safe to share. Never paste secrets into source code, YAML, or documentation.

Alternatively, set environment variables directly in the same PowerShell terminal that runs the application:

```powershell
$env:GEMINI_API_KEY = "your-gemini-key"
$env:GEMINI_MODEL = "your-exact-model-id"
$env:PDF_SERVICES_CLIENT_ID = "your-adobe-client-id"
$env:PDF_SERVICES_CLIENT_SECRET = "your-adobe-client-secret"
```

With these terminal variables set, a `.env` file is optional. Deployment platforms can supply the same environment variables directly. There is no hardcoded Gemini model in the application or example configuration.

## Configure and run

Edit `config.yaml`:

```yaml
input_folder: ./input
output_folder: ./output
protected_persons:
  - Elena Rostova
protected_emails:
  - elena.rostova@example.com  # Replace with the actual protected address
pii_types: [name, email]
gemini:
  chunk_words: 400
highlight:
  color: [1.0, 1.0, 0.0]
  opacity: 0.35
processing:
  retry_count: 3
  ocr_enabled: false
```

Folder paths are relative to the current working directory. Input discovery is nonrecursive and sorts filenames case insensitively, with a deterministic tie breaker; `.PDF` is accepted. Keep output separate from input so previous results are not included in future runs.

```powershell
pdf-redactor --config config.yaml --validate-only
pdf-redactor --config config.yaml
```

Each normal run asks whom to exclude before any service request:

```text
Full names to exclude [Elena Rostova] (separate with semicolons; '-' clears): Alice Smith
```

Enter the excluded person's full name (or multiple names separated by semicolons), for example `Elena Rostova`. A blank response is rejected rather than silently keeping the YAML default. You do not need to supply their email address. Gemini reviews text from all input PDFs to resolve that person's email addresses and alternate name forms, then identifies individual name/email occurrences. Everyone else remains eligible for highlighting. Enter `-` explicitly to clear exclusions. The answer replaces the name list for this run only; `config.yaml` is not rewritten. Interactive runs ignore YAML `protected_emails` so exclusions are based on the selected identities alone. For `--no-prompt` or Python callers, explicit email overrides remain available.

For unattended runs, use the configured YAML exclusions without prompts:

```powershell
pdf-redactor --config config.yaml --no-prompt
```

`--validate-only` never prompts. If interactive input is unavailable or cancelled, processing stops; it does not silently choose exclusions. Python callers can pass keyword-only `protected_persons` and `protected_emails` tuples to `run()` to override YAML, or leave them as `None` to keep YAML defaults.

Validation loads `.env`, checks configuration, and lists input files without requiring service variables or making API calls. It does not verify credentials, model availability, or quotas. Processing requires the Gemini key/model and the Adobe client ID plus either an access token or client secret and reports a missing model or credential before contacting a service. Outputs overwrite the same filenames on successful reruns:

- `output/merged_original.pdf`: Adobe's combined PDF before new highlights.
- `output/merged_highlighted.pdf`: the same pages with highlight annotations.
- `output/audit.json`: per-file page/detection/highlight counts, source page mapping, and checks of page counts, dimensions, protected overlap and highlight coverage.

Exit codes: `0` success, `1` processing failure, `2` configuration/discovery failure, `4` output verification failure. A failed run may leave the original merge or files from an earlier run; check the exit code before using outputs.

## How detection and protection work

1. Discover PDFs, map source pages and merge with Adobe.
2. Extract actual word text and coordinates in native order.
3. Ask Gemini once for all human identities and email ownership, identifying the people excluded by the supplied names.
4. Ground each returned name/address in actual PDF text and match every occurrence locally.
5. Protect the excluded identities' observed names and addresses across all pages.
6. Add precise word quads for everyone else's detected names and addresses. Verify quad placement and exclusion.

`pii_types` supports `name`, `email`, and optional regex-based `employee_id`. Employee IDs have no person-ownership exclusion and are disabled in the supplied configuration.

`GEMINI_MODEL` comes only from the environment. `retry_count` controls additional attempts; processing remains sequential. Legacy chunk settings and the older word-range detector interfaces remain accepted for compatibility, but the production Gemini directory path does not make per-page chunk requests. The full corpus is sent once, subject to the model's context limit.

## Adobe authentication and merge lifecycle

The configured setup uses the client ID and client secret through Adobe's Python SDK. Leave `PDF_SERVICES_ACCESS_TOKEN` empty to select this path. The secret is read from `.env`; it is never embedded in application code. This follows [Adobe's Python quickstart](https://developer.adobe.com/document-services/docs/overview/pdf-services-api/quickstarts/python/) and [official Combine PDF sample](https://github.com/adobe/pdfservices-python-sdk-samples/blob/main/src/combinepdf/combine_pdf.py).

1. Construct `ServicePrincipalCredentials` from `PDF_SERVICES_CLIENT_ID` and `PDF_SERVICES_CLIENT_SECRET`.
2. Initialize `PDFServices` with those credentials. The SDK obtains access tokens for authenticated API calls; there is no need to paste a newly generated token before each run.
3. Upload each source PDF and retain its Adobe asset reference, preserving input order.
4. Add those references to `CombinePDFParams`, create `CombinePDFJob` and submit it.
5. Retrieve `CombinePDFResult`, download the result asset and save the PDF locally.
6. Continue with local word extraction, Gemini identity recognition and annotation.

For direct REST integrations, Adobe documents exchanging the client ID/secret at `POST https://pdf-services.adobe.io/token`, creating/uploading assets, submitting an operation, polling its status and downloading the output in its [getting-started guide](https://developer.adobe.com/document-services/docs/overview/pdf-services-api/gettingstarted). Our optional manual-token path follows that job lifecycle but uses the already supplied access token. A nonempty manual token takes precedence, so clear it when switching to SDK-managed authentication. The client secret and access token serve different purposes and are not interchangeable.

Live Adobe-only verification is recorded in `output/adobe_verification.json`: it reports the authentication path, input count, merged page count and a comparison of extracted text and page dimensions in source order. This verifies merging independently of Gemini availability.

## Gemini pacing and quotas

The screenshot's RPM value `7 / 5` means the peak request rate exceeded five requests per minute, even though token usage and daily request usage were below their respective limits. Each limit applies independently. The application spaces outgoing attempts by `61 / GEMINI_REQUESTS_PER_MINUTE` seconds (12.2 seconds at five RPM). SDK automatic retries are disabled so retries also pass through application pacing. See [Gemini rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) for the independent project allowances. The directory flow makes one request per run (plus bounded retries), so repeated rosters do not create additional per-page requests. The older chunk interface retains its in-memory cache for compatibility.

Pacing is local to one detector instance. Other applications, API keys in the same project, or concurrent pipeline processes can still consume the shared allowance. Restarting a run also restarts its local pacing timer. This controls request bursts; it cannot increase daily quotas or resolve exhausted billing/project allowances. Adjust the environment allowance to match your project, and run one pipeline process at a time.

## Migrating and troubleshooting

If your existing `config.yaml` contains `gemini.model`, remove that line and paste its value into `GEMINI_MODEL` in `.env`. The application rejects the old YAML setting with a migration message so a stale value cannot silently select the wrong model. Keep `gemini.chunk_words` in YAML.

- **`Set GEMINI_MODEL ...`**: fill in the model field, confirm you are running from the folder containing `.env`, and check for an empty terminal override. There is deliberately no default.
- **Missing credential message**: fill in the named environment variable. Adobe's client ID and secret must come from the same credential pair.
- **Gemini identification failure**: confirm the exact model ID is available to your key and supports structured output; check API access, quota and connectivity.
- **Adobe merge failure**: check the token/client ID or credential pair, PDF validity, service quota and network access. HTTP `401` in token mode means the token must be replaced.
- **Updated `.env` appears ignored**: a terminal variable takes precedence. For example, `Remove-Item Env:GEMINI_MODEL -ErrorAction SilentlyContinue` removes the terminal model override for subsequent runs.
- **`No module named dotenv`**: activate your virtual environment and rerun `python -m pip install -e ".[test]"` to install the new dependency.

## Limits and data flow

Full source PDFs are uploaded to Adobe. Extracted word text and protected names are sent to Gemini. Provider quotas and charges apply. The normal audit output contains counts and source paths, not detected names or addresses. The local sample diagnostic `output/sample_execution.json` may also contain the excluded email addresses discovered during the test.

Use searchable PDFs. OCR is not implemented; `ocr_enabled: true` is rejected. Pages without searchable text (including blank pages) stop processing rather than silently reporting complete detection. Password-protected PDFs are rejected. Model extraction can miss names or misclassify text; verification checks annotation mechanics, not perfect semantic recall. Review the highlighted PDF before relying on it. Preexisting source annotations are preserved and may cause verification to fail if they already cover protected information.

## Development

```powershell
python -m pytest
```

Tests use simulated service responses and generated PDFs, so they require no service credentials. Live integration requires valid credentials and service access.

API references: [Adobe Combine PDF](https://developer.adobe.com/document-services/docs/overview/pdf-services-api/howtos/combine-pdf), [Gemini structured output](https://ai.google.dev/gemini-api/docs/structured-output).

## Configure and run

### Commands to run from PowerShell

Open a terminal in the repository root. The installed package and configured .env/config.yaml are required.

powershell
Set-Location D:\Employee-Highlighter

Validate configuration and list input PDFs without calling Adobe or Gemini:

powershell
python -m pdf_redactor.cli --config config.yaml --validate-only

Run the full pipeline with the exclusion prompt:

powershell
python -m pdf_redactor.cli --config config.yaml

At the Full names to exclude prompt, type Elena Rostova and press Enter. Supply only the name; Gemini discovers the corresponding emails. The model is taken from GEMINI_MODEL in .env, currently gemini-3.5-flash.

The installed console command is equivalent:

powershell
pdf-redactor --config config.yaml

Run without prompting, using the protected values in config.yaml:

powershell
python -m pdf_redactor.cli --config config.yaml --no-prompt

Immediately after a run, inspect its exit code and audit:

powershell
$LASTEXITCODE
Get-Content output\audit.json

Exit code 0 means the run and required verification checks passed. The resulting PDF is output\merged_highlighted.pdf.

### Exact command used for the successful sample

From D:\Employee-Highlighter, the following PowerShell command ran the CLI through Python, supplied Elena Rostova to the interactive prompt automatically, and wrote the sample status report. This wrapper is for reproducing the sample; use the interactive command above to select someone else.

powershell
@'
from pathlib import Path
import builtins
import json
from pdf_redactor.cli import main
builtins.input = lambda prompt: 'Elena Rostova'
code = main(['--config', 'config.yaml'])
report = {'mode': 'full_pipeline', 'model': 'gemini-3.5-flash', 'excluded_person': 'Elena Rostova',
          'exit_code': code, 'status': 'success' if code == 0 else 'failed',
          'new_highlighted_pdf_created': code in (0, 4)}
Path('output/sample_execution.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
raise SystemExit(code)
'@ | python -
The model string in this wrapper is a label in the report; the application's actual model selection still comes exclusively from .env. The verified sample processed four input PDFs into eight pages, added 82 highlights, and protected 12 name/email occurrences. All required audit checks passed.

### Document-processing configuration

Edit config.yaml: