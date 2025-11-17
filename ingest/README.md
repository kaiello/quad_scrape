# Ingest Pipeline

This directory contains the scripts for the ingest pipeline.

## Workflow

1.  **Input**: Place raw files (PDFs, images, DOCX, etc.) into the `ingest/input` directory.
2.  **Extraction**: Run the `extract_text_ocr.py` script to extract text from the files in `ingest/input`. The output will be placed in the `ingest/output` directory.
    ```bash
    python ingest/extract_text_ocr.py ingest/input/*
    ```
3.  **Chunking**: Run the `make_chunks_deep.py` script to chunk the extracted text. This script reads from `ingest/output` and writes chunked JSONL files back to `ingest/output`.
    ```bash
    python ingest/make_chunks_deep.py
    ```
4.  **Auditing**: Run the `audit_norm.py` script to audit the extracted text. This script reads from `ingest/output`.
    ```bash
    python ingest/audit_norm.py
    ```
