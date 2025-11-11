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

### 🧩 Step A: Normalization

**Purpose**

This first step transforms raw, extracted document JSON into a stable and structured format. It creates the canonical text units (sentences and chunks) that all downstream steps (embeddings, entity extraction, etc.) will rely on.

This process guarantees deterministic, verifiable IDs for every piece of text and ensures that all downstream annotations can be traced back to the original document text with perfect accuracy.

**Commands**

This step includes two main commands: one to run the normalization and one to validate the results.

```bash
# 1. Run normalization
# Reads from 'inputs/', writes to 'normalized/'
py -m combo normalize inputs/ --out normalized/
```

> # 2\. Validate the output (Recommended in CI)
>
> # Checks for schema and text-slice correctness
>
> py -m combo validate normalized/
>
> ```
>
> **Directory Structure**

> ```
>
> \<project\_root\>/
> ├── inputs/                  \# \<-- INPUT (Raw extracted JSON)
> │   ├── doc\_A.json
> │   └── doc\_B.json
> │
> └── normalized/              \# \<-- OUTPUT (Feeds Step B)
> ├── doc\_A.normalized.json
> ├── doc\_B.normalized.json
> └── \_reports/            \# (Optional reports)
>
> ````
>
> **Arguments & Flags**

> *normalize*

> | Argument | Description | Example |
> | :--- | :--- | :--- |
> | `dir_or_file` (positional) | Required. Input directory or single file containing extracted JSON. | `inputs/` |
> | `--out` | Required. The output directory for normalized files. | `normalized/` |
> | `--quiet` | (Optional) Suppress verbose logging. | |

> *validate*

> | Argument | Description | Example |
> | :--- | :--- | :--- |
> | `dir_or_file` (positional) | Required. Path to the \*.normalized.json files to validate. | `normalized/` |
> | `--fail-fast` | (Optional) Exit on the first validation failure. | |

> **✅ Success Criteria**

> You can confirm this step ran successfully by checking the following:

>   * The `normalize` command completes with an exit code 0.
>   * The output directory (e.g., `normalized/`) is created and contains one `<base>.normalized.json` file for each input document.
>   * The `validate` command (`py -m combo validate normalized/`) also completes with an exit code 0.
>   * Each output file contains the top-level `meta`, `doc`, `sentences`, and `chunks` keys.
>   * The `meta.doc_sha1` (checksum) and `meta.n_sentences`/`n_chunks` counts are present.

> **🔍 Troubleshooting / Triage**

> | Symptom | Likely Cause | Remedy |
> | :--- | :--- | :--- |
> | `normalize` exits with code 2 | Invalid usage. Most commonly, the `--out` path is inside the input path. | Check your paths. Ensure the `--out` directory is fully separate from the input directory. |
> | `validate` exits with code 2 | Validation Failure. The output file is corrupt or invalid. This could be a schema error or, more critically, a "slice-equality" failure (i.e., `sentence.text` does not match the original page text at the stored offsets). | This indicates a bug in the `normalize` step or a corrupt input file. Run `validate` with `--fail-fast` to identify the specific file and error. |
> | `KeyError` on `doc_id` or `pages` | Input JSON is missing required fields. | Ensure your upstream extraction process provides `doc_id` (string) and `pages` (list of strings) for every document. |

---

### 🧠 Step B Overview — Embeddings → Ready for Entity/Relationship (ER)

**Purpose**

Step B converts normalized text chunks from Step A into semantic vector embeddings and accompanying metadata.

This step enables semantic search, clustering, and hybrid retrieval in later phases (Steps C–E), including Knowledge-Graph population and RFI generation.

The step ensures all embeddings are:

>   * **Deterministic** (same text + model → same vector)
>   * **Resumable** (safe to rerun or parallelize)
>   * **Traceable** (every vector linked back to document + chunk + page span)
>   * **Compatible** with both vector stores and graph ingestion

**⚙️ Process Flow**

> | Phase | Description | Key Operations |
> | :--- | :--- | :--- |
> | 1. Input ingestion | Reads `.normalized.json` files from Step A | Each contains structured chunks with `chunk_id`, `doc_id`, `text`, and `pagination` fields. |
> | 2. Embedding generation | Embeds each chunk using a configured model | - Default: `LocalDeterministicAdapter` (64-dim).<br>- Optional: `llama.cpp` model (e.g., `bge-small-en-v1.5-q4_k_m.gguf`) via LangChain / `llama-cpp` binding.<br>- Auto-fallback to local adapter on init failure.<br>- Optional `--force-local` flag to bypass `llama.cpp`. |
> | 3. Token parity guard | Counts tokens by whitespace vs model tokenizer; safely truncates over-length chunks; flags `"truncated": true`. | |
> | 4. Output serialization | Writes embeddings to newline-delimited JSONL files (`*.embedded.jsonl`) | Each record includes `chunk_id`, `doc_id`, `embedding`, `model`, `dim`, `text_sha1`, and optional `page_span`. |
> | 5. Manifest creation | Builds `manifest.json` summarizing the run | Records model, version, row count, doc IDs, created timestamp. |
> | 6. Run reporting | Generates run report JSON under `_reports/` | Contains totals, avg latency, retries, truncations, and error summary. |
> | 7. Optional indexing | Builds lightweight `.npz` or FAISS index | Quick cosine-similarity search for local ANN validation. |

**Inputs**

> | Source | Format | Purpose |
> | :--- | :--- | :--- |
> | Step A outputs | `*.normalized.json` | Text chunks with metadata ready for embedding. |
> | Embedding model | `.gguf` (optional, via `llama.cpp`) or deterministic adapter | Defines vector dimension and semantic space. |
> | Config params | CLI flags (`--batch`, `--timeout`, `--max-retries`, etc.) | Control batching, retries, and performance. |

**Outputs**

> | Artifact | Location | Contents / Use |
> | :--- | :--- | :--- |
> | `*.embedded.jsonl` | `emb/` (or specified `--out`) | One JSON row per chunk → semantic vectors + metadata. |
> | `manifest.json` | `emb/` | Model name, row count, creation timestamp, doc IDs. |
> | `run_report.json` | `emb/_reports/` | Telemetry, errors, warnings, notes (e.g., fallback). |
> | `embeddings.npz` (optional) | `idx/` | Matrix (vecs) + ID array (ids) for instant similarity tests. |

**🧾 Example CLI Commands**

> Local deterministic embedding (current production path):

> ```bash
> py -m combo embed tmp_norm --out tmp_emb_local --adapter local --dim 64 --batch 64 --timeout 30
> py -m combo index tmp_emb_local --out tmp_idx
> ````
>
> Llama.cpp (future retry once binding fixed):
>
> ```bash
> py -m combo doctor --adapter llama-cpp ^
>  --llama-model-path "C:\Users\kenai\OneDrive\Documents\Projects\models\bge-small-en-v1.5-q4_k_m.gguf" ^
>  --n-ctx 4096 --n-threads 8 --seed 0 ^
>  --json-out emb_reports\doctor_bge_small_retry.json
> ```
>
> **✅ Review / Handoff Summary for Agent**
>
> | Review Focus | Expected Outcome |
> | :--- | :--- |
> | Functionality | Embeddings deterministically written; manifest + report created; fallback works. |
> | Resilience | `.tmp` resume logic verified; pipeline stays green even if `llama.cpp` fails. |
> | Traceability | Every vector links back to `doc_id` + `chunk_id` + `text_sha1`. |
> | Artifacts ready for Step C | `*.embedded.jsonl` + `manifest.json` feed directly into entity/relation extraction. |
>
> **Step B in one line**
>
> > Transforms normalized text chunks into deterministic, metadata-rich vector embeddings—ready for semantic retrieval, entity/relation extraction, and hybrid graph + LLM reasoning.

---

### 🔗 Step C: Within-Document Coreference

This step links pronouns and referring expressions (e.g., *it, they, this system*) to their antecedent entity mentions inside the same document. This ensures all mentions that describe the same thing share a common `resolved_entity_id`.

**Command:**

```bash
py -m combo coref tmp_er \
 --out tmp_coref \
 --max-sent-back 3 \
 --max-mentions-back 30
```

**Arguments & Flags:**

> | Argument | Description | Example |
> | :--- | :--- | :--- |
> | `er-dir` (positional) | Required. Input directory from Step B (ER). | `tmp_er` |
> | `--out` | Required. Output directory for coref results. | `tmp_coref` |
> | `--max-sent-back` | (Optional) Sentences to look backward. | `3` (default) |
> | `--max-mentions-back` | (Optional) Mention window size. | `30` (default) |

**✅ How to Verify Success:**

> You can confirm the step ran successfully by checking the following:

>   * The command finishes with an exit code 0.
>   * The output directory (e.g., `tmp_coref/`) is created.
>   * The `tmp_coref/` directory contains an `.entities.jsonl` file for every input file.
>   * Each output `.entities.jsonl` file has the identical line count as its corresponding input file.
>   * The `tmp_coref/_reports/run_report.json` file exists and shows non-zero values for `mentions` and `pronouns_total`.

---

### 📝 Step C.5: 5W(H) Aggregation

**Purpose**

This step builds a per-document summary of **Who / What / When / Where / How**. It works by aggregating the entity mentions from the previous steps (ER + Coref) into a single, compact JSON record for each document, which is ideal for quick database ingestion or review.

**Command**

This is the recommended command, which uses the outputs from Step C (Coref) and the optional Normalization step for the best results.

```bash
py -m combo fourw tmp_er \
 --coref-dir tmp_coref \
 --normalized-dir tmp_norm \
 --out tmp_4w \
 --things-labels DEVICE,PRODUCT,VEHICLE,WEAPON,SYSTEM,TOOL,SOFTWARE,COMPONENT,MATERIAL \
 --min-thing-count 1
```

**Directory Structure**

```
<project_root>/
├── tmp_coref/               # <-- INPUT (Recommended)
│   ├── doc_A.entities.jsonl
│   └── ...
├── tmp_norm/                # <-- INPUT (Optional)
│   └── ...
│
└── tmp_4w/                  # <-- OUTPUT
    ├── doc_A.docprops.jsonl
    ├── doc_B.docprops.jsonl
    └── _reports/
        └── run_report.json
```

**Arguments & Flags**

> | Argument | Description | Example |
> | :--- | :--- | :--- |
> | `er_dir` (positional) | Fallback input. Path to Step B (ER) outputs. Used if `--coref-dir` is missing. | `tmp_er` |
> | `--coref-dir` | **Recommended input**. Path to Step C (Coref) outputs. | `tmp_coref` |
> | `--normalized-dir` | Optional input. Path to normalized doc metadata (for mime, filename, etc.). | `tmp_norm` |
> | `--out` | Required. The output directory for 5W(H) summaries. | `tmp_4w` |
> | `--things-labels` | (Config) Comma-separated list of entity labels to include in the "How" bucket. | `DEVICE,PRODUCT,...` |
> | `--min-thing-count` | (Config) Minimum mentions for a "thing" to be included. | `1` (default) |
> | `--allow-other-into-how` | (Flag) If set, includes entities with the `OTHER` label in the "How" bucket. | |
> | `--max-fallback-dates` | (Config) Max dates to find via regex if no `DATE` entities exist. | `5` (default) |

**✅ Success Criteria**

> You can confirm this step ran successfully by checking the following:

>   * The command completes with an exit code 0.
>   * The output directory (e.g., `tmp_4w/`) is created.
>   * The directory contains `<base>.docprops.jsonl` files.
>   * The `tmp_4w/_reports/run_report.json` file is created and shows non-zero `docs` and `totals`.
>   * If you inspect a `docprops.jsonl` file, you see all five main keys: `who`, `what`, `when`, `where`, and `how`.
>   * In the report, `used_coref` should be `true` if you provided the `tmp_coref` directory.

**🔍 Troubleshooting / Triage**

> | Symptom | Likely Cause | Remedy |
> | :--- | :--- | :--- |
> | "how" bucket is empty or missing items | The `--things-labels` list doesn't match the labels from your ER step. | Check your ER (Step B) output labels and update the `--things-labels` flag to match. |
> | "who" or "how" has split entities (e.g., "ACME" and "it" are separate) | Coref was not used, or the mentions were missing `resolved_entity_id`. | Ensure you are passing `--coref-dir tmp_coref` and check the `run_report.json` to see `used_coref: true`. |
> | "when" bucket is empty | No `DATE` or `TIME` entities were found by Step B. | Provide `--normalized-dir tmp_norm` so the step can fall back to regex on the `text_preview`. |
> | "what" bucket has `doc_type: "unknown"` | The `--normalized-dir` was not provided or had no mime/filename info. | This is okay, but for better "what" info, provide the `tmp_norm` directory. |

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
