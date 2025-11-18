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
import torch
from transformers import AutoModelForImageTextToText, AutoProcessor
from PIL import Image
from unstructured.documents.elements import Text
import io

from unstructured.partition.auto import partition
from unstructured.staging.base import elements_to_json

def setup_logging(verbose: bool) -> None:
    """Configure logging based on verbosity."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

# Load model globally so we don't reload it for every single file (slow!)
# device_map="auto" will automatically use your GPU.
MODEL_ID = "nanonets/Nanonets-OCR2-3B"
try:
    processor = AutoProcessor.from_pretrained(MODEL_ID, trust_remote_code=True)
    model = AutoModelForImageTextToText.from_pretrained(
        MODEL_ID,
        torch_dtype=torch.bfloat16,  # Uses less VRAM than float32
        device_map="auto",           # Auto-selects your GPU
        trust_remote_code=True,
        # attn_implementation="flash_attention_2" # SPEED BOOST (Remove if it errors)
    )
    print(f"✅ Nanonets Model Loaded on {model.device}")
except Exception as e:
    print(f"⚠️ Model failed to load (do you have a GPU?): {e}")
    model = None

def nanonets_ocr_vlm(file_path):
    """
    Runs Nanonets OCR2 (Qwen2.5-VL) on a local image/PDF page.
    Returns structured Markdown text (tables, headers, etc).
    """
    if model is None:
        return None

    # 1. Convert file_path to an Image object
    # (If file_path is a PDF, you might need to convert the first page to an image using pdf2image)
    try:
        image = Image.open(file_path).convert("RGB")
    except Exception:
        return None

    # 2. The "Magic" Prompt
    # This specific prompt tells the model to act like an OCR engine
    prompt_text = (
        "Extract the text from the above document as if you were reading it naturally. "
        "Return the tables in html format. "
        "Return the equations in LaTeX representation. "
        "Identify checkboxes using ☐ and ☑."
    )

    # 3. Prepare inputs
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": prompt_text},
            ],
        }
    ]
    
    # 4. Run Inference
    text_inputs = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(
        text=[text_inputs],
        images=[image],
        padding=True,
        return_tensors="pt"
    ).to(model.device)

    # 5. Generate
    generated_ids = model.generate(
        **inputs,
        max_new_tokens=4096  # Allow it to write a full page of text
    )
    
    # 6. Decode output
    output_text = processor.batch_decode(
        generated_ids, 
        skip_special_tokens=True, 
        clean_up_tokenization_spaces=False
    )[0]

    # Strip out the prompt echo if necessary (depends on processor version)
    return output_text

def ingest_file(file_path: str) -> List[dict]:
    logging.info("Partitioning file: %s", file_path)
    try:
        # 1. Try standard Unstructured partitioning
        elements = partition(file_path)
        
        # 2. Check if it failed to find text (e.g., it's a scanned image)
        # If total text length is < 50 chars, assume it's an image/scan
        total_text = "".join([e.text for e in elements if hasattr(e, "text")])
        
        if len(total_text.strip()) < 50:
            logging.info("Initial partitioning yielded minimal text. Attempting VLM OCR.")
            
            # Only run Nanonets if it is an image (PDFs require extra handling not present here yet)
            if file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.tiff')):
                nanonets_result = nanonets_ocr_vlm(file_path)
                
                if nanonets_result:
                    # Create a single "Text" element containing the Markdown output
                    # This ensures the downstream 'write_output' function works
                    logging.info("✅ VLM OCR Successful")
                    return [Text(text=nanonets_result)]
            else:
                logging.warning("File is a PDF/Doc scan, but Nanonets VLM logic currently only supports Images. Skipping VLM.")

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
