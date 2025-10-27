# quad-scrape

Universal text extractor with OCR for PDFs, images, and Office files (DOCX, PPTX, XLSX, CSV). Prefers a vision-transformer backend (TrOCR) when available, with graceful fallbacks to Tesseract or EasyOCR.

## Features
- PDF: embedded text via PyMuPDF or PyPDF; OCR on rendered pages when needed
- Images: OCR via Transformers, Tesseract, or EasyOCR
- DOCX/PPTX/XLSX: lightweight OOXML parsing (no heavy docx/pptx/xlsx libs)
- CSV: direct parsing
- Output: text to stdout/file or JSON (with per-page structure for PDFs)

## Requirements
- Python 3.8–3.12
- Poetry installed (https://python-poetry.org/)
- Optional system tools:
  - Tesseract OCR (for `--backend tesseract`) — add `tesseract.exe` to PATH
  - Poppler (only if pdf2image fallback is used) — add Poppler `bin` to PATH

## Setup
```bash
poetry lock
poetry install --no-root
```
On Windows (PowerShell) with the `py` launcher:
```powershell
py -m poetry lock
py -m poetry install --no-root
```

## Usage
- Single file to stdout:
```bash
poetry run python extract_text_ocr.py "path/to/file.pdf"
```
- Aggregated outputs to files (creates `outputs/`):
```bash
poetry run python extract_text_ocr.py "data/*" --out outputs/extracted.txt
poetry run python extract_text_ocr.py "data/*" --format json --pretty --out outputs/extracted.json
```
- Per-file outputs in a directory:
```bash
poetry run python extract_text_ocr.py "data/*" --out outputs/
# produces outputs/<filename>.<ext>.txt for each input
```
- OCR backend selection:
```bash
poetry run python extract_text_ocr.py scan.png --backend transformer   # TrOCR via transformers+torch
poetry run python extract_text_ocr.py scan.png --backend tesseract     # requires Tesseract installed
poetry run python extract_text_ocr.py scan.png --backend easyocr
```
- PDF rasterization controls (for OCR):
```bash
poetry run python extract_text_ocr.py scanned.pdf --dpi 300 --max-pages 10
```
- Verbose logging:
```bash
poetry run python extract_text_ocr.py file.pdf --verbose
```

Windows examples (PowerShell):
```powershell
py -m poetry run python extract_text_ocr.py "data/*" --out outputs/extracted.txt
py -m poetry run python extract_text_ocr.py "data/*" --format json --pretty --out outputs/extracted.json
```

## Notes
- PDFs: Tries embedded text first; if missing, rasterizes and performs OCR.
- PPTX normalization: Text runs are joined per paragraph for more natural reading; explicit line breaks are preserved.
- JSON output: Single file → one object; multiple files → array. PDFs include `pages` plus combined `text`.
- First-time transformer OCR runs will download model weights (internet required).

## Troubleshooting
- Console Unicode on Windows: The tool writes UTF-8 and falls back to bytes if needed.
- Tesseract not found: Install Tesseract and ensure `tesseract.exe` is on PATH.
- Poppler missing: Only needed when PyMuPDF isn’t available and pdf2image fallback is used.

## Local Embeddings (Step B)
- Current status: Functional via local deterministic adapter. llama.cpp embeddings are blocked on Windows (llama-cpp-python 0.3.16) with error `llama_decode returned -1`. The `embed` CLI auto‑falls back to the local adapter if llama.cpp init fails and annotates the run report with notes.
- Health check:
  - Auto-pick: `py -m combo doctor --adapter llama-cpp --models-dir "C:\Users\kenai\OneDrive\Documents\Projects\models"`
  - Explicit path: `py -m combo doctor --adapter llama-cpp --llama-model-path "C:\path\to\model.gguf"`
- Embed locally (deterministic):
  - `py -m combo embed normalized --out emb --adapter local --dim 64`
- Retry llama.cpp when a newer wheel is available (or on WSL/Linux):
  - `py -m poetry run pip install --upgrade llama-cpp-python`
  - `py -m combo doctor --adapter llama-cpp --llama-model-path "C:\path\to\model.gguf"`


## Project Files
- `extract_text_ocr.py` — CLI and extraction logic
- `pyproject.toml` — Poetry configuration
- `requirements.txt` — Optional pip-based dependency list
- `data/` — Put your inputs here
- `outputs/` — Script writes results here in examples above
