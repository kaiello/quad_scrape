# quad-scrape

Universal text extractor and structured ingestion pipeline for Knowledge-Graph construction.

## Purpose

The purpose of this project is to provide a comprehensive and extensible pipeline for converting raw, unstructured data from various file formats into a structured format suitable for knowledge graph construction. It handles text extraction, normalization, embedding, and entity linking, creating a foundation for downstream analysis and querying.

> **Pipeline Stages:** Convert raw files → normalized JSON → chunked JSONL → vector embeddings → entity linking → graph-ready data.

---

## 🔧 Core Modules

| Module | Purpose |
|---|---|
| `combo.coref` | Handles within-document coreference resolution to link mentions of the same entity. |
| `combo.docprops` | Aggregates document properties into the "Who, What, When, Where, How" (4W-H) framework. |
| `combo.embed` | Manages the conversion of text chunks into vector embeddings using various models. |
| `combo.er` | Performs entity and relation extraction from text. |
| `combo.io` | Defines the data contracts and I/O operations for the pipeline. |
| `combo.link` | Links entities across documents to a canonical registry. |
| `combo.normalize` | Normalizes and segments extracted text into sentences and chunks. |

---

## ⚙️ Features

| Stage | Purpose |
|--------|----------|
| Extraction (Step A) | OCR + lightweight parsing for PDFs, images, DOCX/PPTX/XLSX/CSV |
| Validation (A.2) | Enforce deterministic, schema-checked JSON |
| Embeddings (Step B) | Convert normalized chunks into vector embeddings |
| Linking (Step D) | Map mentions → canonical entities via SQLite registry |
| Extensible | Modular design (normalize → validate → embed → link → Neo4j) |

---

## 🧰 Requirements
- Python 3.8 – 3.12  
- Poetry (https://python-poetry.org/)  
- Optional system tools  
  - Tesseract OCR (`tesseract.exe` on PATH)  
  - Poppler (`bin` on PATH; only for pdf2image fallback)

---

## ⚙️ Setup

```powershell
# PowerShell (recommended)
py -m poetry lock
py -m poetry install --no-root
```

> 💡 If you see `Import-Module posh-git` errors, either
> `Install-Module posh-git -Scope CurrentUser -Force`
> or comment out that line in `$PROFILE`.

---

## 🚀 Local Workflow (Steps A → D)

### Step A — Normalize & Validate

```powershell
py -m poetry run python -m combo normalize "tests/fixtures/coref" --out "tmp_norm"
py -m poetry run python -m combo validate "tmp_norm"
```

✅ Produces `tmp_norm/*.normalized.json` and validation summary (`failures: 0`).

---

## 📖 How to Use the Program

This section provides detailed instructions on how to run each stage of the `quad-scrape` pipeline, including the expected inputs, outputs, and how to verify the results.

### Stage 1: Normalize & Validate (Step A)

This stage takes raw extracted JSON files, segments them into sentences and chunks, and saves them as normalized JSON files.

*   **Inputs:**
    *   A directory containing JSON files with extracted text. Each JSON file can contain a single document or a list of documents. The text can be in a `pages` array (for multi-page documents) or a single `text` field.
    *   Example Input Location: `tests/fixtures/coref/`

*   **Command:**
    ```powershell
    py -m poetry run python -m combo normalize <input_directory> --out <output_directory>
    py -m poetry run python -m combo validate <output_directory>
    ```
    *   `<input_directory>`: The path to the directory containing your input JSON files.
    *   `<output_directory>`: The path where the normalized JSON files will be saved.

*   **Outputs:**
    *   Normalized JSON files, with one file per input document. The output filename is derived from the input filename (e.g., `input.json` -> `input.normalized.json`).
    *   Output Location: The `<output_directory>` you specify. For the example workflow, this is `tmp_norm/`.

*   **How to View and Verify:**
    *   **View:** The output files are standard JSON. You can open them in any text editor. You will see a structured format containing `meta`, `doc`, `sentences`, `chunks`, and `images` keys.
    *   **Verify:** Run the `combo validate` command on the output directory. A successful run will print a summary with `failures: 0`. This confirms that the output files adhere to the expected schema and internal consistency checks (e.g., sentence slicing).

### Stage 2: Chunk & Embed (Step B)

This stage prepares the normalized data for embedding and then generates vector embeddings for each chunk.

*   **Inputs:**
    *   A directory of normalized JSON files from the previous stage.
    *   Input Location: `tmp_norm/` (using the output from Step A).

*   **Commands:**
    1.  **Chunking:**
        ```powershell
        py .\make_chunks_deep.py
        ```
        This helper script reads from `tmp_norm/` and creates chunked JSONL files.
    2.  **Embedding:**
        ```powershell
        py -m poetry run python -m combo embed <chunk_directory> --out <embedding_output_directory> --force-local
        ```
        *   `<chunk_directory>`: The directory containing the chunked JSONL files (e.g., `tmp_chunks/`).
        *   `<embedding_output_directory>`: The directory where the embedded JSONL files will be saved.

*   **Outputs:**
    *   **Chunks:** JSONL files (`.jsonl`) where each line is a chunk.
        *   Output Location: `tmp_chunks/`
    *   **Embeddings:** JSONL files (`.embedded.jsonl`) where each line contains a chunk's metadata and its corresponding vector embedding. A `_reports/run_report.json` file is also created.
        *   Output Location: The `<embedding_output_directory>` you specify (e.g., `tmp_emb_local/`).

*   **How to View and Verify:**
    *   **View:** The chunk and embedding files are JSONL, so you can view them line by line in a text editor.
    *   **Verify:** Check the `_reports/run_report.json` file inside the embedding output directory. A successful run will show `"errors": 0` and `"written" > 0`.

### Stage 3: Link Entities (Step D)

This stage links entities from your documents to a central, canonical knowledge base (a SQLite database).

*   **Inputs:**
    *   A directory with entity files (`.entities.jsonl`). For the example, we use the pre-prepared fixtures.
    *   A SQLite database file to act as the entity registry.
    *   Input Location: `tests/fixtures/coref/`
    *   Registry Location: `step_D_tests/data_registry.sqlite`

*   **Command:**
    ```powershell
    py -m poetry run python -m combo link <entity_directory> --registry <registry_path> --out <linking_output_directory>
    ```
    *   `<entity_directory>`: Directory with `.entities.jsonl` files.
    *   `<registry_path>`: Path to your SQLite registry file.
    *   `<linking_output_directory>`: Directory to save the linked entity results.

*   **Outputs:**
    *   A `linked.entities.jsonl` file containing the linked entities. Each line represents a canonical entity found in the documents, linking it to all its mentions.
    *   A `_reports/run_report.json` file with summary statistics.
    *   The SQLite registry file will be updated with any new entities found.
    *   Output Location: The `<linking_output_directory>` you specify (e.g., `step_D_tests/linked_runA/`).

*   **How to View and Verify:**
    *   **View:** The output is a JSONL file. You can also inspect the SQLite database using a tool like DB Browser for SQLite to see the `entities` and `aliases` tables.
    *   **Verify:** Check the `_reports/run_report.json` in the output directory. A successful run will have `"docs" > 0` and `"entities" > 0`.

---

### Step B — Chunk & Embed

1. Chunk normalized data:

   ```powershell
   py .\make_chunks_deep.py
   ```

   → creates `tmp_chunks/*.jsonl`
2. Embed using local deterministic adapter:

   ```powershell
   py -m poetry run python -m combo embed "tmp_chunks" `
     --out "tmp_emb_local" `
     --force-local --dim 64 --batch 64 --timeout 30
   ```

   → check `_reports/run_report.json` → `"errors": 0`, `"written" > 0`.

---

### Step D — Link Entities

```powershell
py -m poetry run python -m combo link "tests/fixtures/coref" `
  --registry "step_D_tests/data_registry.sqlite" `
  --out "step_D_tests/linked_runA" `
  --link-conf 0.75
```

✅ Produces `linked.*.jsonl` and `_reports/run_report.json` (`docs > 0`, `entities > 0`).

---

### Directory Overview

```
quad-scrape/
├─ tests/fixtures/coref/            # sample input
├─ tmp_norm/                        # normalized JSON
├─ tmp_chunks/                      # JSONL chunks
├─ tmp_emb_local/                   # embeddings
├─ step_D_tests/linked_runA/        # linked outputs
├─ make_chunks_deep.py              # helper chunker
├─ audit_norm.py                    # schema auditor
└─ README.md
```

---

## 🧪 Validation Checklist

| Step | Dir                             | Key Artifacts                 | Pass Criteria  |
| ---- | ------------------------------- | ----------------------------- | -------------- |
| A    | `tmp_norm/`                     | `*.normalized.json`           | Validation OK  |
| B    | `tmp_chunks/`, `tmp_emb_local/` | `*.jsonl`, `*.embedded.jsonl` | `written > 0`  |
| D    | `step_D_tests/linked_runA/`     | `linked.*.jsonl`              | `entities > 0` |

---

### 🧾 Print a Run Summary

After Steps A → D, print a one-line conclusion and a Markdown table:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\print_summary.ps1
```

Expected output (example):

| Metric           |       Value |
| ---------------- | ----------: |
| Normalized files |           7 |
| Chunk files      |           7 |
| Embedded files   |           7 |
| Linked files     |           1 |
| Embed written    |           7 |
| Embed errors     |           0 |
| Link docs        |           1 |
| Link entities    |           2 |
| Adapter          |       local |
| Notes            | force_local |
| Status           |     SUCCESS |

Conclusion:
`Status: SUCCESS — Normalized=7 | Chunks=7 | Embedded=7 (written=7, adapter=local, notes=force_local) | Linking: docs=1, entities=2`

> Tip: On Windows, run PowerShell with `-NoProfile` to avoid profile warnings (e.g., `posh-git`):
>
> ```powershell
> powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\print_summary.ps1
> powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\assert_success.ps1
> ```

---

### ✅ CI Gate / Assert Success

After the summary, enforce a pass/fail gate for Steps A→D:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\assert_success.ps1
```

* Exit 0 → SUCCESS (embed errors = 0, link errors = 0, link entities > 0)
* Exit 1 → FAIL (CI stops)

#### GitHub Actions example

```yaml
- name: Print quad-scrape summary
  shell: pwsh
  run: powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\print_summary.ps1

- name: Assert quad-scrape success
  shell: pwsh
  run: powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\assert_success.ps1 -RequireEmbedWritten
```

#### Azure Pipelines example

```yaml
- powershell: |
    powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\print_summary.ps1
    powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\assert_success.ps1 -RequireEmbedWritten
  displayName: 'Summarize & Assert quad-scrape'
```

---

## 🧩 Embeddings Details

* Default: Local deterministic adapter (Windows-safe).
* Fallback: If `llama.cpp` fails (`llama_decode = -1`), the CLI logs `"force_local"`.
* Health check:

  ```powershell
  py -m combo doctor --adapter llama-cpp --models-dir "C:\Users\kenai\...\models"
  ```
* Enable llama.cpp (Linux / WSL):

  ```bash
  poetry run pip install --upgrade llama-cpp-python
  py -m combo doctor --adapter llama-cpp --llama-model-path "/path/to/model.gguf"
  ```

---

## ⚡ PowerShell Notes

| Shell      | Continuation | Example                                                                |
| ---------- | ------------ | ---------------------------------------------------------------------- |
| PowerShell | Backtick `   | ``py -m poetry run python -m combo link "..." \`<br>  --registry ...`` |
| Bash / WSL | Backslash \  | `py -m poetry run python -m combo link "..." \<br>  --registry ...`    |

---

## 🧠 Next Step (E)

> Graph Integration → Neo4j

* Generate Cypher DDL from linked JSON.
* Upsert nodes/edges into Neo4j Aura or local instance.
* Validate via `MATCH (n) RETURN count(n)` and lineage checks.

---

## 🧾 Troubleshooting

| Symptom                                        | Likely Cause                 | Fix                                        |
| ---------------------------------------------- | ---------------------------- | ------------------------------------------ |
| `Missing expression after unary operator '--'` | Using Bash `\` in PowerShell | Use backtick `                             |
| `written: 0` in embed report                   | Inputs unchunked or cached   | Run `make_chunks_deep.py`, use new out dir |
| No text extracted                              | PDFs/images lacked OCR       | Run `extract_text_ocr.py` first            |
| `posh-git` warning                             | PowerShell profile module    | Install or comment out                     |

---

## 🤖 Codex Handoff Instructions

Task: Run and validate Steps A → D of the `quad-scrape` pipeline locally.

Environment:

* Working dir: project root (`C:\Users\kenai\OneDrive\Documents\Projects\quad_scrape`)
* Shell: PowerShell (Windows)
* Python 3.12 + Poetry 2.2.1 already installed

Procedure:

1. Run setup:

   ```powershell
   py -m poetry lock
   py -m poetry install --no-root
   ```
2. Execute Steps A → D exactly as shown above.
3. On completion:

   * Output `tmp_emb_local\_reports\run_report.json`
   * Output `step_D_tests\linked_runA\_reports\run_report.json`
   * Print counts of normalized, chunked, embedded, and linked files.
4. Print run summary:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\print_summary.ps1
   ```
5. Enforce the gate (non-zero exit on failure):

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\assert_success.ps1
   ```

Optional strict mode (fail if embed written == 0):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\assert_success.ps1 -RequireEmbedWritten
```

Success Criteria:

* Validation returns 0 failures
* Embed report shows `"written" > 0`
* Link report shows `"entities" > 0`
* `tools/assert_success.ps1` exits 0

Artifacts to Retain:

* `tmp_norm/`, `tmp_chunks/`, `tmp_emb_local/`, `step_D_tests/linked_runA/`
* Log output with timestamps and any warning notes (e.g., `"force_local"`)
* Exit status of `tools/assert_success.ps1` (report pass/fail)

If any step fails:

* Re-run with new output directory names (avoid caching).
* If embed = 0 written, rerun `make_chunks_deep.py` then re-embed.
* If normalization fails, ensure input path is `tests/fixtures/coref`.

---

✅ Next Step:  
Commit this updated `README.md` (and ensure `make_chunks_deep.py` + `audit_norm.py` exist in repo).  
Then hand it to Codex — it can follow the “Codex Handoff Instructions” verbatim to replicate your working local run.
