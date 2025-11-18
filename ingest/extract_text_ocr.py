#!/usr/bin/env python3
"""
Refactored universal text extractor for documents using the `unstructured` library
and a local Nanonets OCR2 (VLM) for complex financial tables.
"""
from __future__ import annotations
import argparse
import logging
import os
import glob
from typing import List, Optional
import torch
from transformers import AutoModelForImageTextToText, AutoProcessor
from PIL import Image
from unstructured.documents.elements import Text
from unstructured.partition.auto import partition
from unstructured.staging.base import elements_to_json
import pypdfium2 as pdfium 

def setup_logging(verbose: bool) -> None:
    """Configure logging based on verbosity."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

# -------------------------------------------------------------------------
# MODEL LOADING (Global)
# -------------------------------------------------------------------------
MODEL_ID = r"C:\nanonets_model"

print(f"🔍 DEBUG: Script is attempting to load model from: {MODEL_ID}")

try:
    # PROCESSOR
    processor = AutoProcessor.from_pretrained(MODEL_ID, trust_remote_code=True)
    
    # MODEL - OPTIMIZED LOADING
    # We use 'low_cpu_mem_usage=True' to stream weights directly to the GPU,
    # bypassing the System RAM bottleneck that causes Error 1455.
    model = AutoModelForImageTextToText.from_pretrained(
        MODEL_ID,
        torch_dtype=torch.bfloat16,
        trust_remote_code=True,
        low_cpu_mem_usage=True,  # <--- THE CRITICAL FIX
        device_map="cuda"        # <--- Load directly to GPU
    )
    
    print(f"✅ Nanonets Model Loaded on {model.device}")

except Exception as e:
    print(f"⚠️ Model failed to load: {e}")
    model = None
    processor = None
# -------------------------------------------------------------------------
# HELPER FUNCTIONS
# -------------------------------------------------------------------------

def has_financial_signals(elements: List[dict]) -> bool:
    """
    Heuristic: Returns True if the document contains financial table indicators.
    Keywords: Funding, FY(Year), $, Cost, Budget
    """
    # Combine all text to scan it quickly
    full_text = " ".join([e.text for e in elements if hasattr(e, "text")]).lower()
    
    # 1. Check for specific keywords
    keywords = ["funding", "cost share", "fiscal year", "fy2", "budget", "milestones"]
    keyword_hits = sum(1 for k in keywords if k in full_text)
    
    # 2. Check for currency symbols (often indicates tables)
    currency_hits = full_text.count("$")
    
    # Trigger Logic: 
    if keyword_hits >= 2 or currency_hits >= 3:
        logging.info(f"💰 Financial Data Detected (Keywords: {keyword_hits}, $: {currency_hits}). Upgrading to VLM.")
        return True
    return False

def nanonets_ocr_vlm(file_path: str) -> Optional[str]:
    """
    Runs Nanonets OCR2 on images OR PDFs (by converting them first).
    """
    if model is None:
        logging.warning("VLM requested but model is not loaded.")
        return None

    # Helper: Get list of images (Handle Image vs PDF)
    images = []
    if file_path.lower().endswith(".pdf"):
        try:
            pdf = pdfium.PdfDocument(file_path)
            # Iterate through pages (Process all pages)
            for i in range(len(pdf)): 
                page = pdf[i]
                # scale=2 ensures high res for small text reading
                bitmap = page.render(scale=2) 
                pil_image = bitmap.to_pil()
                images.append(pil_image)
        except Exception as e:
            logging.error(f"PDF Conversion failed: {e}")
            return None
    else:
        # It's already an image
        try:
            images.append(Image.open(file_path).convert("RGB"))
        except Exception as e:
            logging.error(f"Image open failed: {e}")
            return None

    # Run Inference on each page
    full_output = []
    
    # The Prompt: Explicitly ask for HTML tables for financial data
    prompt_text = (
        "Read the text naturally. "
        "If there are tables or grids (especially financial or funding data), "
        "represent them strictly as HTML tables <table>...</table>. "
        "Preserve structure."
    )

    logging.info(f"🧠 Processing {len(images)} pages with Nanonets VLM...")

    for img in images:
        try:
            messages = [
                {"role": "user", "content": [{"type": "image", "image": img}, {"type": "text", "text": prompt_text}]}
            ]
            
            text_inputs = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            inputs = processor(text=[text_inputs], images=[img], padding=True, return_tensors="pt").to(model.device)
            
            generated_ids = model.generate(**inputs, max_new_tokens=4096)
            output_text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
            full_output.append(output_text)
        except Exception as e:
            logging.error(f"Inference failed on page: {e}")

    return "\n\n".join(full_output)

def ingest_file(file_path: str) -> List[dict]:
    """
    Main ingestion logic:
    1. Fast parse with Unstructured.
    2. Check for scans or financial data.
    3. If found, upgrade to VLM OCR.
    """
    logging.info("Partitioning file: %s", file_path)
    try:
        # 1. Fast Pass (Unstructured)
        elements = partition(file_path)
        
        # 2. Check 1: Is it a scan? (Low text count)
        total_text = "".join([e.text for e in elements if hasattr(e, "text")])
        is_scan = len(total_text.strip()) < 50
        
        # 3. Check 2: Does it have complex financial tables?
        is_financial = has_financial_signals(elements)

        if is_scan or is_financial:
            logging.info(f"🚀 Triggering VLM Upgrade (Scan: {is_scan}, Financial: {is_financial})")
            
            nanonets_result = nanonets_ocr_vlm(file_path)
            
            if nanonets_result:
                logging.info("✅ VLM Extraction Successful")
                # Return as a single massive chunk of structured markdown/HTML/Text
                # Downstream chunking (chunk_by_title) will handle splitting this later
                return [Text(text=nanonets_result)]

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

# -------------------------------------------------------------------------
# MAIN EXECUTION
# -------------------------------------------------------------------------

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    p = argparse.ArgumentParser(description="Extract text and metadata from documents using unstructured.")
    p.add_argument("input", help="Path to a file or a glob pattern (e.g., 'input/*.pdf')")
    p.add_argument("--out", default="output", help="Output directory for JSON files.")
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