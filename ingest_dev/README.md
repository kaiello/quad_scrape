# Multimodal/Deep Ingestion Pipeline (V2)

## 1. Overview
This is the "V2" pipeline using **Docling** for better layout parsing and asset extraction. Unlike the previous pipeline, this version treats **Tables** and **Images** as first-class citizens in the graph.

## 2. The Scripts

### `extract_v4_1_docling.py`
**Purpose:** Multimodal extraction using Docling.

**Key Features:**
- **Smart Figure Merging:** Reconstructs fragmented images (e.g. "quads") and snaps them to the nearest section header to provide context (e.g. Slide Title).
- **Structure Preservation:** Exports separate CSVs for tables and cropped PNGs for figures.

**Output:** Creates nested folders for each document (e.g., `output/doc_name/figures/` and `output/doc_name/tables/`).

### `make_chunks_deep.py`
**Purpose:** Recursive chunking and asset injection.

**Key Features:**
- **Hybrid Chunking:** Combines standard text chunks (using `chunk_by_title` from `unstructured`) with asset chunks.
- **Asset Injection:** Recursively scans the nested `tables/` and `figures/` folders and injects them as distinct chunks into the `.jsonl` stream.
- **Table Embeddings:** Embeds raw CSV content directly into the text field for immediate searchability.
- **Flattening:** Consolidates deep nested inputs from the extraction phase into a flat `ingest/chunks/` directory.

## 3. Usage Guide

### Step 1: Extract
Run the extraction script on your input files (PDFs or Images).

```bash
# Example: Process all PDFs in ingest/input/
python3 ingest_dev/extract_v4_1_docling.py "ingest/input/*.pdf" --out ingest/output
```

### Step 2: Chunk and Inject Assets
Run the chunking script to process the extracted content and assets.

```bash
# Example: Chunk content from ingest/output/ and save to ingest/chunks/
python3 ingest_dev/make_chunks_deep.py --input ingest/output --output ingest/chunks
```

## 4. Output Schema
The pipeline generates a JSONL file for each document, containing a stream of chunks.
New metadata fields include:

- **`metadata.type`**: Indicates the content type.
    - `"text"`: Standard text content.
    - `"table"`: Table data (often with CSV content in the `text` field).
    - `"image"`: Image assets (text field may be a placeholder or description).

Example chunk structure:
```json
{
  "doc_id": "doc_name",
  "chunk_id": 0,
  "text": "...",
  "metadata": {
    "filename": "...",
    "file_path": "...",
    "type": "text",
    "page_number": 1
  }
}
```
