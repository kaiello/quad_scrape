# quad-scrape

Universal text extractor and structured ingestion pipeline for Knowledge-Graph construction.

> Purpose: Convert raw files → normalized JSON → chunked JSONL → vector embeddings → entity linking → graph-ready data.

---

## 🔧 Features

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

### Step C: Within-Document Coreference

This step links pronouns and referring expressions (e.g., *it, they, this system*) to their antecedent entity mentions inside the same document. This ensures all mentions that describe the same thing share a common `resolved_entity_id`.

**Command:**

```bash
py -m combo coref tmp_er \
  --out tmp_coref \
  --max-sent-back 3 \
  --max-mentions-back 30
```

**Arguments & Flags:**

| Argument | Description | Example |
| :--- | :--- | :--- |
| `er-dir` (positional) | **Required.** Input directory from Step B (ER). | `tmp_er` |
| `--out` | **Required.** Output directory for coref results. | `tmp_coref` |
| `--max-sent-back` | (Optional) Sentences to look backward. | `3` (default) |
| `--max-mentions-back` | (Optional) Mention window size. | `30` (default) |

**✅ How to Verify Success:**

You can confirm the step ran successfully by checking the following:

1.  The command finishes with an **exit code 0**.
2.  The output directory (e.g., `tmp_coref/`) is created.
3.  The `tmp_coref/` directory contains an **`.entities.jsonl` file for every input file**.
4.  Each output `.entities.jsonl` file has the **identical line count** as its corresponding input file.
5.  The `tmp_coref/_reports/run_report.json` file exists and shows non-zero values for `mentions` and `pronouns_total`.

---

### 🧩 Step C.5: 5W(H) Aggregation

### Purpose

This step builds a per-document summary of **Who / What / When / Where / How**. It works by aggregating the entity mentions from the previous steps (ER + Coref) into a single, compact JSON record for each document, which is ideal for quick database ingestion or review.

### Command

This is the recommended command, which uses the outputs from **Step C (Coref)** and the optional **Normalization** step for the best results.

```bash
py -m combo fourw tmp_er \
  --coref-dir tmp_coref \
  --normalized-dir tmp_norm \
  --out tmp_4w \
  --things-labels DEVICE,PRODUCT,VEHICLE,WEAPON,SYSTEM,TOOL,SOFTWARE,COMPONENT,MATERIAL \
  --min-thing-count 1
```

### Directory Structure

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

### Arguments & Flags

| Argument | Description | Example |
| :--- | :--- | :--- |
| `er_dir` (positional) | **Fallback input.** Path to Step B (ER) outputs. Used if `--coref-dir` is missing. | `tmp_er` |
| `--coref-dir` | **Recommended input.** Path to Step C (Coref) outputs. | `tmp_coref` |
| `--normalized-dir` | **Optional input.** Path to normalized doc metadata (for mime, filename, etc.). | `tmp_norm` |
| `--out` | **Required.** The output directory for 5W(H) summaries. | `tmp_4w` |
| `--things-labels` | (Config) Comma-separated list of entity labels to include in the **"How"** bucket. | `DEVICE,PRODUCT,...` |
| `--min-thing-count` | (Config) Minimum mentions for a "thing" to be included. | `1` (default) |
| `--allow-other-into-how`| (Flag) If set, includes entities with the `OTHER` label in the "How" bucket. | |
| `--max-fallback-dates`| (Config) Max dates to find via regex if no DATE entities exist. | `5` (default) |

-----

### ✅ Success Criteria

You can confirm this step ran successfully by checking the following:

  * The command completes with an **exit code 0**.
  * The output directory (e.g., `tmp_4w/`) is created.
  * The directory contains **`<base>.docprops.jsonl`** files.
  * The `tmp_4w/_reports/run_report.json` file is created and shows non-zero `docs` and `totals`.
  * If you inspect a `docprops.jsonl` file, you see all five main keys: `who`, `what`, `when`, `where`, and `how`.
  * In the report, `used_coref` should be `true` if you provided the `tmp_coref` directory.

-----

### 🔍 Troubleshooting / Triage

| Symptom | Likely Cause | Remedy |
| :--- | :--- | :--- |
| **"how"** bucket is empty or missing items | The `--things-labels` list doesn't match the labels from your ER step. | Check your ER (Step B) output labels and update the `--things-labels` flag to match. |
| **"who"** or **"how"** has split entities (e.g., "ACME" and "it" are separate) | Coref was not used, or the mentions were missing `resolved_entity_id`. | Ensure you are passing `--coref-dir tmp_coref` and check the `run_report.json` to see `used_coref: true`. |
| **"when"** bucket is empty | No `DATE` or `TIME` entities were found by Step B. | Provide `--normalized-dir tmp_norm` so the step can fall back to regex on the `text_preview`. |
| **"what"** bucket has `doc_type: "unknown"` | The `--normalized-dir` was not provided or had no mime/filename info. | This is okay, but for better "what" info, provide the `tmp_norm` directory. |

-----

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
