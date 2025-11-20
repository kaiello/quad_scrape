# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "unstructured",
# ]
# ///
import os
import json
import logging
import argparse
from pathlib import Path
from typing import List, Dict, Any

from unstructured.chunking.title import chunk_by_title
from unstructured.staging.base import elements_from_json

def setup_logging(verbose: bool = False) -> None:
    """
    Configures the logging level and format.

    Args:
        verbose (bool): If True, sets logging level to DEBUG; otherwise INFO.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

def create_asset_chunk(
    doc_id: str,
    asset_path: Path,
    asset_type: str,
    chunk_index: int
) -> Dict[str, Any]:
    """
    Creates a standardized chunk record for non-text assets (Tables/Images).

    Constructs a JSON-compatible dictionary representing a chunk, including
    metadata about the asset source and type.

    Args:
        doc_id (str): The document identifier.
        asset_path (Path): Path to the asset file (image or csv).
        asset_type (str): Type of asset, e.g., 'table' or 'image'.
        chunk_index (int): The sequential ID for this chunk.

    Returns:
        Dict[str, Any]: A dictionary representing the asset chunk.
    """
    # Relative path for portability
    try:
        rel_path = asset_path.relative_to(os.getcwd())
    except ValueError:
        rel_path = asset_path

    metadata = {
        "filename": asset_path.name,
        "file_path": str(rel_path),
        "type": asset_type,
        "page_number": None
    }

    # Attempt to extract page number from standard naming convention: "{base}_pg{N}_{type}_{I}"
    # Example: doc1_pg3_smart_fig_1.png
    parts = asset_path.stem.split('_')
    for part in parts:
        if part.startswith('pg') and part[2:].isdigit():
            metadata["page_number"] = int(part[2:])
            break

    # For Tables: The "text" is the raw CSV content (good for basic embedding)
    # For Images: The "text" is a placeholder or filename (needs VLM captioning later if not present)
    text_content = f"[{asset_type.upper()}: {asset_path.name}]"

    if asset_type == "table":
        try:
            with open(asset_path, "r", encoding="utf-8") as f:
                # limit CSV text to avoid token limits, or take first 10 lines
                csv_content = f.read()
                text_content = f"Table Data:\n{csv_content}"
        except Exception as e:
             # REFACTOR: Catch specific exception and log warning
             logging.warning(f"Could not read table content from {asset_path}: {e}")

    return {
        "doc_id": doc_id,
        "chunk_id": chunk_index,
        "text": text_content,
        "metadata": metadata,
    }

def main() -> int:
    """
    Main function to process and chunk JSON files + Assets recursively.

    Reads extracted JSON files, chunks the text content, and injects
    corresponding table and figure assets as separate chunks.

    Returns:
        int: Exit code (0 for success, 1 for failure).
    """
    parser = argparse.ArgumentParser(description="Chunk extracted JSON files and assets.")
    parser.add_argument("--input", default="ingest/output", help="Directory containing extracted output folders")
    parser.add_argument("--output", default="chunks", help="Directory to save chunked JSONL files")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()

    setup_logging(args.verbose)

    input_dir = Path(args.input)
    output_dir = Path(args.output)

    if not input_dir.exists():
        logging.error("Input directory not found: %s", input_dir)
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)

    # Find all source JSON files (the main entry point for each doc)
    json_files = list(input_dir.rglob("*.json"))

    if not json_files:
        logging.warning("No .json files found in %s (recursive search).", input_dir)
        return 0

    logging.info(f"Found {len(json_files)} documents to process.")

    written_chunks = 0
    processed_files = 0

    for file_path in json_files:
        # Skip reports or non-content JSONs
        if "_report" in file_path.name:
            continue

        logging.info("Processing Document: %s", file_path.name)
        doc_id = file_path.stem

        # The folder containing this json and its assets
        doc_source_dir = file_path.parent

        chunk_records = []
        current_chunk_id = 0

        try:
            # --- 1. Process Text Chunks (from JSON) ---
            elements = elements_from_json(filename=str(file_path))
            text_chunks = chunk_by_title(
                elements,
                combine_text_under_n_chars=500,
                max_characters=1500
            )

            for chunk in text_chunks:
                chunk_dict = chunk.to_dict()
                # Ensure metadata contains type 'text'
                meta = chunk_dict.get("metadata", {})
                meta["type"] = "text"

                chunk_records.append({
                    "doc_id": doc_id,
                    "chunk_id": current_chunk_id,
                    "text": chunk_dict.get("text", ""),
                    "metadata": meta,
                })
                current_chunk_id += 1

            logging.debug(f"  - Generated {len(text_chunks)} text chunks")

            # --- 2. Process Table Assets (from tables/*.csv) ---
            tables_dir = doc_source_dir / "tables"
            if tables_dir.exists():
                table_files = sorted(list(tables_dir.glob("*.csv")))
                for tf in table_files:
                    record = create_asset_chunk(doc_id, tf, "table", current_chunk_id)
                    chunk_records.append(record)
                    current_chunk_id += 1
                logging.debug(f"  - Injected {len(table_files)} table assets")

            # --- 3. Process Image Assets (from figures/*.png) ---
            figures_dir = doc_source_dir / "figures"
            if figures_dir.exists():
                image_files = sorted(list(figures_dir.glob("*.png")))
                for imgf in image_files:
                    record = create_asset_chunk(doc_id, imgf, "image", current_chunk_id)
                    chunk_records.append(record)
                    current_chunk_id += 1
                logging.debug(f"  - Injected {len(image_files)} image assets")

            # --- 4. Write Combined JSONL ---
            if not chunk_records:
                logging.warning("No content found for file: %s", file_path)
                continue

            output_path = output_dir / f"{doc_id}.jsonl"
            with open(output_path, "w", encoding="utf-8") as f:
                for record in chunk_records:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    written_chunks += 1

            logging.info("  -> Wrote %d total chunks (Text+Tables+Images) to %s", len(chunk_records), output_path.name)
            processed_files += 1

        except Exception as e:
            # REFACTOR: Catch specific exceptions where possible, or at least log traceback
            logging.error("Failed to process %s: %s", file_path, e, exc_info=True)

    logging.info("-" * 30)
    logging.info("Processing Complete.")
    logging.info("Files Processed: %d", processed_files)
    logging.info("Total Chunks Written: %d", written_chunks)
    logging.info("Output Directory: %s", output_dir.resolve())

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
