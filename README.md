# Universal Text Extractor and Ingestion Pipeline

## 1. Purpose

This repository contains a universal text extraction and structured ingestion pipeline designed for Knowledge-Graph construction. It provides a modular, extensible framework for converting raw, unstructured data from various file formats into a structured, graph-ready format. The pipeline manages text extraction, normalization, embedding, entity linking, and more, creating a solid foundation for downstream analysis and querying.

**Pipeline Stages:** Raw Files → Normalized JSON → Chunked JSONL → Vector Embeddings → Entity Linking → Graph-Ready Data.

---

## 2. Getting Started

### Prerequisites

- **Python:** 3.8 – 3.12
- **Poetry:** [Official Documentation](https://python-poetry.org/)
- **Optional Tools:**
  - Tesseract OCR (`tesseract.exe` on PATH)
  - Poppler (`bin` on PATH for `pdf2image` fallback)

### Installation

1. **Lock Dependencies:**
   ```powershell
   py -m poetry lock
   ```
2. **Install:**
   ```powershell
   py -m poetry install --no-root
   ```

> **Note:** If you encounter `Import-Module posh-git` errors in PowerShell, run `Install-Module posh-git -Scope CurrentUser -Force` or comment out the import line in your `$PROFILE`.

---

## 3. Core Concepts

The pipeline is organized into modular stages, each with a specific responsibility:

| Module | Description |
|---|---|
| `combo.normalize` | Normalizes and segments extracted text into sentences and chunks. |
| `combo.embed` | Converts text chunks into vector embeddings using various models. |
| `combo.coref` | Handles within-document coreference resolution. |
| `combo.docprops` | Aggregates document properties into a "Who, What, When, Where, How" (4W-H) framework. |
| `combo.er` | Performs entity and relation extraction. |
| `combo.link` | Links entities across documents to a canonical registry. |
| `combo.io` | Defines data contracts and I/O operations. |

---

## 3.1. Pipeline Stages

Each pipeline stage is executed as a Python module, ensuring a consistent and scriptable workflow.

| Stage | Command | Purpose |
|---|---|---|
| **A: Normalize** | `py -m combo.normalize` | Extracts text and metadata from source files into a standardized `.normalized.json` format. |
| **A.2: Validate** | `py -m combo.validate` | Audits normalized files against a strict schema to ensure data integrity. |
| **B: Embed** | `py -m combo.embed` | Converts text chunks into vector embeddings and stores them in `.embedded.jsonl`. |
| **C: Coreference** | `py -m combo.coref` | Resolves entity coreferences within each document. |
| **C.5: Aggregation**| `py -m combo.docprops`| Aggregates document properties into the 4W-H framework. |
| **D: Link** | `py -m combo.link` | Links entities across documents to a canonical registry. |

## 4. Command-Line Interface (CLI)

The pipeline is executed via Python modules. Below are examples for each stage.

### Step A: Normalize & Validate

```powershell
py -m poetry run python -m combo normalize "tests/fixtures/coref" --out "tmp_norm"
py -m poetry run python -m combo validate "tmp_norm"
```

- **Success:** Produces `tmp_norm/*.normalized.json` and a validation summary with `failures: 0`.

### Step B: Chunk & Embed

1. **Chunk Data:**
   ```powershell
   py .\\make_chunks_deep.py
   ```
   - **Output:** `tmp_chunks/*.jsonl`

2. **Embed Chunks:**
   ```powershell
   py -m poetry run python -m combo embed "tmp_chunks" `
     --out "tmp_emb_local" `
     --force-local --dim 64 --batch 64 --timeout 30
   ```
   - **Success:** `_reports/run_report.json` shows `"errors": 0` and `"written" > 0`.

### Step D: Link Entities

```powershell
py -m poetry run python -m combo link "tests/fixtures/coref" `
  --registry "step_D_tests/data_registry.sqlite" `
  --out "step_D_tests/linked_runA" `
  --link-conf 0.75
```

- **Success:** Produces `linked.*.jsonl` and a report with `docs > 0` and `entities > 0`.

---

## 5. Development

### Directory Structure

```
quad-scrape/
├─ src/combo/                     # Main source code
├─ tests/                         # Unit and integration tests
├─ tools/                         # Helper scripts
├─ pyproject.toml                 # Project dependencies
└─ README.md
```

### Running Tests

To run the full test suite:

```powershell
py -m poetry run pytest
```

### CI/CD

The pipeline includes scripts for continuous integration:

- **`tools/print_summary.ps1`**: Prints a one-line summary and a Markdown table of the run.
- **`tools/assert_success.ps1`**: Enforces a pass/fail gate, exiting with `0` on success and `1` on failure.

---

## 6. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Missing expression` | Using Bash `\` in PowerShell | Use backtick `` ` `` instead. |
| `written: 0` in embed report | Unchunked or cached inputs | Run `make_chunks_deep.py` and use a new output directory. |
| No text extracted | Missing OCR data | Run `extract_text_ocr.py` first. |
