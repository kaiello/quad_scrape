import os
import json
import glob
import pathlib
import logging
from typing import List, Optional

from unstructured.chunking.title import chunk_by_title
from unstructured.staging.base import elements_from_json, elements_to_dicts

def setup_logging(verbose: bool = False) -> None:
    """Configure logging based on verbosity."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

def main():
    """Main function to process and chunk JSON files."""
    setup_logging()

    in_dir = "ingest/output"
    out_dir = "ingest/output"

    if not os.path.isdir(in_dir):
        logging.error("Input directory not found: %s", in_dir)
        return 1

    os.makedirs(out_dir, exist_ok=True)

    json_files = glob.glob(os.path.join(in_dir, "*.json"))
    if not json_files:
        logging.warning("No .json files found in %s to process.", in_dir)
        return 0

    written_chunks = 0
    for file_path in json_files:
        logging.info("Processing file: %s", file_path)

        try:
            # Load elements from the JSON file produced by extract_text_ocr.py
            elements = elements_from_json(filename=file_path)

            # Chunk the elements by title
            chunks = chunk_by_title(elements)

            if not chunks:
                logging.warning("No chunks were created for file: %s", file_path)
                continue

            # Prepare for JSONL output
            doc_id = os.path.basename(file_path)
            out_path = os.path.join(out_dir, f"{pathlib.Path(doc_id).stem}.jsonl")

            with open(out_path, "w", encoding="utf-8") as f:
                for i, chunk in enumerate(chunks):
                    chunk_dict = chunk.to_dict()
                    record = {
                        "doc_id": doc_id,
                        "chunk_id": i,
                        "text": chunk_dict.get("text", ""),
                        "metadata": chunk_dict.get("metadata", {}),
                    }
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    written_chunks += 1

            logging.info("Wrote %d chunks to %s", len(chunks), out_path)

        except Exception as e:
            logging.error("Failed to process %s: %s", file_path, e, exc_info=True)

    logging.info("Total chunks written: %d", written_chunks)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
