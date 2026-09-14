# Usage Guide

Employee PDF Highlighter merges PDFs and adds removable highlights for detected human names and email addresses. It preserves page content and does not erase or redact information. Gemini identifies people and observed text forms; PyMuPDF matches those forms to word coordinates and creates the annotations locally. Adobe PDF Services combines multiple source PDFs.

## Quick start

Complete [SETUP.md](SETUP.md) first. From the repository root, with the virtual environment active:

```powershell
pdf-redactor --config config.yaml --validate-only
pdf-redactor --config config.yaml
```

The first command validates the YAML and lists direct-child PDFs in `input/` without contacting external services. The second command prompts for protected names, processes the PDFs, and writes results to `output/`.

For unattended execution:

```powershell
pdf-redactor --config config.yaml --no-prompt
```

This uses `protected_persons` and `protected_emails` from `config.yaml` exactly as configured.

## Input and output contract

Place source files directly in `input/`. Discovery is nonrecursive, accepts `.pdf` case-insensitively, and sorts filenames deterministically. Do not place generated output in the input folder.

Each normal run produces:

| File | Description |
| --- | --- |
| `output/merged_original.pdf` | Combined source PDF before this run's highlights. |
| `output/merged_highlighted.pdf` | Combined PDF with eligible highlights added. |
| `output/audit.json` | Detection counts, source-page mapping, and verification fields. |

Highlights are annotations, so the underlying text remains readable and removable in a compatible PDF viewer. Protected detections are retained in the audit but are not highlighted.

## Configuration

The normal configuration is copied from `config.example.yaml`:

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
employee_id_patterns:
  - "\\bEMP[- ]?\\d{4,10}\\b"
highlight:
  color: [1.0, 1.0, 0.0]
  opacity: 0.35
processing:
  concurrency: 1
  retry_count: 3
  continue_on_error: false
  ocr_enabled: false
```

### Protected values

- `protected_persons` contains exact names to exclude from highlighting.
- `protected_emails` contains exact addresses to protect, including addresses whose ownership may be ambiguous from document context.
- Interactive mode lets the operator replace the configured protected names for the current run. Enter names separated by semicolons, or `-` to clear them.
- `--no-prompt` prevents interactive input and uses YAML values.

Protection is conservative: a protected person can have name variants and owned addresses identified by Gemini, but a similar email username alone does not establish ownership. Add an address explicitly when it must always be protected.

### Highlight settings

`highlight.color` uses three RGB values from `0.0` through `1.0`. `highlight.opacity` must be greater than `0` and no greater than `1`. The default is a yellow highlight at `0.35` opacity.

### Processing settings

`processing.retry_count` controls additional Gemini attempts for malformed responses and selected transient service failures. `processing.concurrency` is validated but the production pipeline remains sequential. `processing.continue_on_error` is retained as a configuration field; processing failures are not silently skipped. OCR is currently unsupported.

## Environment variables

The application loads `.env` from the current working directory. Run from the repository root. Existing process environment variables take precedence over `.env`.

| Variable | Required | Purpose |
| --- | --- | --- |
| `GEMINI_API_KEY` | Yes | Authenticates Gemini requests. |
| `GEMINI_MODEL` | Yes | Exact available Gemini model ID; there is no default. |
| `GEMINI_REQUESTS_PER_MINUTE` | No | Local request pacing limit; defaults to `5`. |
| `PDF_SERVICES_CLIENT_ID` | Yes | Adobe project client ID. |
| `PDF_SERVICES_ACCESS_TOKEN` | One of token/secret | Temporary Adobe bearer token; takes precedence when set. |
| `PDF_SERVICES_CLIENT_SECRET` | One of token/secret | Adobe secret for SDK-managed authentication. |

Do not put `gemini.model` in YAML. The application rejects that legacy setting; put the model ID in `GEMINI_MODEL` instead.

## Processing behavior

1. Validate configuration and discover source PDFs.
2. Inspect source pages and build source-to-merged page mappings.
3. Combine PDFs through Adobe when more than one input exists. A single input is copied without an unnecessary combine request.
4. Extract searchable words and their page coordinates with PyMuPDF.
5. Send the extracted corpus to Gemini to identify human names, emails, ownership, and protected identities.
6. Match returned values to actual PDF words locally, retaining precise word rectangles.
7. Add eligible highlight annotations to a separate output PDF.
8. Verify page counts, dimensions, protected intersections, and eligible highlight counts; write `audit.json`.

The application does not use local capitalization heuristics or spaCy name detection. It does not OCR scanned PDFs. The full extracted corpus is sent to the configured Gemini model, so document size must fit that model's context limit.

## Audit and exit codes

`audit.json` contains `files` and `verification`. Detection counts represent entity occurrences, including protected candidates; repeated occurrences are counted again. A successful CLI run requires these checks to pass:

- `page_count_match`
- `page_dimensions_match`
- `protected_information_not_highlighted`
- `all_eligible_detections_highlighted`

| Exit code | Meaning |
| ---: | --- |
| `0` | Processing and required verification checks passed. |
| `1` | Processing failed or interactive input was cancelled. |
| `2` | Configuration or input discovery failed. |
| `4` | Processing completed but required verification failed. |

## Operational limits

- Only direct-child PDFs in `input/` are processed.
- PDFs must contain searchable text; OCR is not implemented.
- Adobe combine operations are batched at a maximum of 20 PDFs per operation.
- Gemini requests are paced locally and may retry transient failures, but quotas and billing limits still apply.
- Adobe access tokens are not refreshed automatically.
- Outputs are written in stages; keep the exit code and audit timestamp when diagnosing interruptions.