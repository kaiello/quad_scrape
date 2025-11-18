#!/usr/bin/env python3
"""
Refactored universal text extractor for documents using the `unstructured` library.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import glob
from typing import List, Optional

from unstructured.partition.auto import partition
from unstructured.staging.base import elements_to_json

def setup_logging(verbose: bool) -> None:
    """Configure logging based on verbosity."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

def nanonets_ocr_vlm(file_path: str) -> Optional[str]:
    """
    Placeholder for a local Vision-Language Model (VLM) like Nanonets OCR2.
    This function will be implemented later to handle scanned documents
    or low-quality text extractions.
    """
    logging.warning("Nanonets OCR2 requires GPU - feature pending. File: %s", file_path)
    # In the future, this would invoke a local OCR model and return the text.
    return None

def ingest_file(file_path: str) -> List[dict]:
    """
    Ingests a single file using `unstructured.partition.auto.partition`.
    If partitioning returns minimal text, it will eventually fall back to
    a more advanced OCR model.

    Args:
        file_path: The path to the file to ingest.

    Returns:
        A list of dictionaries representing the unstructured document elements.
    """
    logging.info("Partitioning file: %s", file_path)
    try:
        elements = partition(file_path)
        # Future logic: check if elements contain substantial text.
        # If not, it might be a scanned document.
        # For now, we'll just return the results from partition.
        # Example check:
        # if not any(e.text.strip() for e in elements):
        #     logging.info("Initial partitioning yielded no text. Attempting VLM OCR.")
        #     nanonets_result = nanonets_ocr_vlm(file_path)
        #     # Process nanonets_result if it's not None

        return elements
    except Exception as e:
        logging.error("Failed to partition %s: %s", file_path, e, exc_info=True)
        return []

def write_output(elements: List[dict], out_path: str, pretty: bool = False):
    """
    Writes the extracted elements to a JSON file.
    """
    parent = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(parent, exist_ok=True)

    json_str = elements_to_json(elements, indent=2 if pretty else None)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(json_str)
    logging.info("Wrote output to: %s", out_path)

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    p = argparse.ArgumentParser(description="Extract text and metadata from documents using unstructured.")
    p.add_argument("input", help="Path to a file or a glob pattern (e.g., 'input/*.pdf')")
    p.add_argument("--out", default="ingest/output", help="Output directory for JSON files.")
    p.add_argument("--pretty", action="store_true", help="Pretty-print the JSON output.")
    p.add_argument("--verbose", action="store_true", help="Enable verbose logging.")
    return p.parse_args(argv)

def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point for the script."""
    args = parse_args(argv)
    setup_logging(args.verbose)

    # Expand glob patterns
    files = glob.glob(args.input)
    if not files:
        logging.error("No files matched the input pattern: %s", args.input)
        return 1

    for file_path in files:
        if not os.path.isfile(file_path):
            logging.warning("Skipping non-file path: %s", file_path)
            continue

        elements = ingest_file(file_path)

        if elements:
            # Create a unique output filename
            base_name = os.path.basename(file_path)
            output_filename = f"{base_name}.json"
            output_path = os.path.join(args.out, output_filename)

            write_output(elements, output_path, pretty=args.pretty)
        else:
            logging.warning("No elements were extracted from %s.", file_path)

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
