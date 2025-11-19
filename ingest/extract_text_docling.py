#!/usr/bin/env python3
"""
Refactored universal text extractor using IBM Docling with TableFormer (Table Transformer)
and Tesseract CLI (Windows-Safe) for robust "any document" ingestion.
"""
from __future__ import annotations
import argparse
import logging
import os
import glob
from typing import List, Optional

# Docling Imports
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions, 
    TableFormerMode, 
    TesseractCliOcrOptions,  # <--- CRITICAL FIX: Use CLI wrapper, not Python binding
    EasyOcrOptions
)
from docling.datamodel.document import TableItem, TextItem, SectionHeaderItem, ListItem

# Unstructured Imports (for Schema compatibility)
from unstructured.documents.elements import Text, Table, Title, ListItem as UnstructuredListItem
from unstructured.staging.base import elements_to_json

def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

# -------------------------------------------------------------------------
# PIPELINE CONFIGURATION (The "Heavy Lifting")
# -------------------------------------------------------------------------
def get_configured_converter() -> DocumentConverter:
    """
    Configures Docling to use the TableFormer (Transformer) model and OCR.
    Uses Tesseract CLI to avoid Windows compilation issues with tesserocr.
    """
    # Configure Pipeline Options specifically for PDFs
    pipeline_options = PdfPipelineOptions()
    
    # 1. Enable Table Structure Recognition (The "Table Transformer")
    # This handles complex financial tables, row spans, and col spans.
    pipeline_options.do_table_structure = True
    pipeline_options.table_structure_options.mode = TableFormerMode.ACCURATE
    
    # 2. Enable OCR (for scanned docs/images)
    pipeline_options.do_ocr = True
    
    # FIX: Use TesseractCliOcrOptions instead of TesseractOcrOptions.
    # This requires 'tesseract' to be in your System PATH.
    # If this still fails, replace with EasyOcrOptions() as a fallback.
    pipeline_options.ocr_options = TesseractCliOcrOptions() 
    
    # 3. Image Generation (Optional: helpful if you need to debug table crops later)
    pipeline_options.generate_page_images = False

    # Bind these options to the PDF format
    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )

# Initialize Converter Global
doc_converter = get_configured_converter()

# -------------------------------------------------------------------------
# MAPPING LOGIC
# -------------------------------------------------------------------------
def map_docling_to_unstructured(docling_doc) -> List[dict]:
    """
    Maps Docling's hierarchical structure to flat Unstructured Elements.
    """
    unstructured_elements = []

    for item, level in docling_doc.iterate_items():
        
        if isinstance(item, TableItem):
            # Docling's TableFormer has already reconstructed the structure.
            # We export the HTML to preserve that structure for downstream LLMs.
            html_content = item.export_to_html()
            
            element = Table(
                text=item.export_to_dataframe().to_csv(index=False),
                text_as_html=html_content
            )
            # Add metadata if available (e.g., page number)
            if hasattr(item, "prov") and item.prov:
                element.metadata.page_number = item.prov[0].page_no
            
            unstructured_elements.append(element)

        elif isinstance(item, SectionHeaderItem):
            unstructured_elements.append(Title(text=item.text))

        elif isinstance(item, ListItem):
            unstructured_elements.append(UnstructuredListItem(text=item.text))

        elif isinstance(item, TextItem):
            unstructured_elements.append(Text(text=item.text))
            
    return unstructured_elements

def ingest_file(file_path: str) -> List[dict]:
    logging.info("Processing file: %s", file_path)
    try:
        # 1. Convert using the configured pipeline
        conversion_result = doc_converter.convert(file_path)
        
        # 2. Map to standard format
        elements = map_docling_to_unstructured(conversion_result.document)
        
        table_count = sum(1 for e in elements if isinstance(e, Table))
        logging.info(f"✅ Success: {len(elements)} elements extracted ({table_count} Tables found via TableFormer).")
        return elements

    except Exception as e:
        logging.error("Failed to process %s: %s", file_path, e, exc_info=True)
        return []

def write_output(elements: List[dict], out_path: str, pretty: bool = False):
    parent = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(parent, exist_ok=True)
    os.makedirs(parent, exist_ok=True)
    json_str = elements_to_json(elements, indent=2 if pretty else None)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(json_str)
    logging.info("Output saved to: %s", out_path)

# -------------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description="Docling Ingestion with TableFormer & OCR")
    p.add_argument("input", help="File path or glob pattern (e.g., *.pdf)")
    p.add_argument("--out", default="output", help="Output directory")
    p.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    p.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    args = p.parse_args()

    setup_logging(args.verbose)
    files = glob.glob(args.input)
    if not files:
        logging.error("No files found for pattern: %s", args.input)
        return

    for file_path in files:
        if os.path.isfile(file_path):
            elements = ingest_file(file_path)
            if elements:
                base_name = os.path.basename(file_path)
                output_path = os.path.join(args.out, f"{base_name}.json")
                write_output(elements, output_path, pretty=args.pretty)

if __name__ == "__main__":
    main()