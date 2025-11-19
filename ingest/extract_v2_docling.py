#!/usr/bin/env python3
"""
Integrated Docling Extractor v2
Combines:
1. Robust OCR & TableFormer (from your original script)
2. Granite Docling VLM Pipeline (optional via --vlm)
3. Asset Extraction (Figures, CSVs, Annotated Pages)
4. Unstructured.io Schema Export (JSON)
"""
from __future__ import annotations
import argparse
import logging
import os
import glob
import time
from pathlib import Path
from typing import List, Optional, Union

# Data Handling
import pandas as pd
from PIL import Image, ImageDraw

# Docling Core
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions, 
    TableFormerMode, 
    TesseractCliOcrOptions,
    VlmPipelineOptions
)
from docling.datamodel.document import (
    DoclingDocument, 
    TableItem, 
    TextItem, 
    SectionHeaderItem, 
    ListItem,
    PictureItem
)
# VLM Support
from docling.pipeline.vlm_pipeline import VlmPipeline
from docling.datamodel import vlm_model_specs

# Unstructured Support
from unstructured.documents.elements import Text, Table, Title, ListItem as UnstructuredListItem, ElementMetadata
from unstructured.staging.base import elements_to_json

# Logging Setup
def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")
    return logging.getLogger(__name__)

_log = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# 1. PIPELINE CONFIGURATION
# -------------------------------------------------------------------------
def get_configured_converter(use_vlm: bool = False) -> DocumentConverter:
    """
    Returns a converter. 
    - Default: Uses TableFormer (Accurate) + Tesseract CLI (Robust).
    - VLM Mode: Uses Granite Docling for complex visual layouts.
    """
    if use_vlm:
        _log.info("🚀 Initializing VLM Pipeline (Granite Docling)...")
        # Configure VLM options (using Granite Docling)
        # Switch to GRANITEDOCLING_HUGGINGFACE if not on Mac M-series
        pipeline_options = VlmPipelineOptions(
            vlm_options=vlm_model_specs.GRANITEDOCLING_MLX 
        )
        
        return DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_cls=VlmPipeline, 
                    pipeline_options=pipeline_options
                ),
                InputFormat.IMAGE: PdfFormatOption(
                    pipeline_cls=VlmPipeline,
                    pipeline_options=pipeline_options
                )
            }
        )
    else:
        _log.info("🔧 Initializing Standard Pipeline (TableFormer + Tesseract)...")
        # Standard robust configuration for text/tables
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_table_structure = True
        pipeline_options.table_structure_options.mode = TableFormerMode.ACCURATE
        pipeline_options.do_ocr = True
        pipeline_options.ocr_options = TesseractCliOcrOptions() # Windows-safe CLI
        pipeline_options.generate_page_images = True # Needed for annotation/cropping

        return DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )

# -------------------------------------------------------------------------
# 2. ASSET EXTRACTION (Visuals & Tables)
# -------------------------------------------------------------------------
def annotate_pages(doc: DoclingDocument, output_dir: Path):
    """Draws bounding boxes around detected elements on page images."""
    pages_dir = output_dir / "annotated_pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    
    for page_no, page in doc.pages.items():
        if page.image:
            # Create a copy to draw on
            img = page.image.image.copy() # Access underlying PIL image
            draw = ImageDraw.Draw(img)
            
            # Helper to draw boxes
            def draw_box(item, color):
                if hasattr(item, "prov") and item.prov:
                    for p in item.prov:
                        if p.page_no == page_no:
                            draw.rectangle(p.bbox.as_tuple(), outline=color, width=3)

            # Color Code:
            # Blue = Text, Red = Tables, Green = Figures
            for item in doc.texts: draw_box(item, "blue")
            for item in doc.tables: draw_box(item, "red")
            for item in doc.pictures: draw_box(item, "green")

            out_path = pages_dir / f"page_{page_no}.png"
            img.save(out_path)

def export_assets(doc: DoclingDocument, output_dir: Path, base_name: str):
    """Exports Tables to CSV and Figures to PNG."""
    tables_dir = output_dir / "tables"
    figures_dir = output_dir / "figures"
    tables_dir.mkdir(exist_ok=True)
    figures_dir.mkdir(exist_ok=True)

    # 1. Export Tables
    for i, table in enumerate(doc.tables):
        try:
            table_df = table.export_to_dataframe()
            csv_path = tables_dir / f"{base_name}_table_{i+1}.csv"
            table_df.to_csv(csv_path, index=False)
        except Exception as e:
            _log.warning(f"Could not export Table {i+1}: {e}")

    # 2. Export Figures (Cropping)
    for i, picture in enumerate(doc.pictures):
        try:
            if picture.prov:
                page_no = picture.prov[0].page_no
                page_obj = doc.pages.get(page_no)
                if page_obj and page_obj.image:
                    # Crop using bbox
                    bbox = picture.prov[0].bbox.as_tuple()
                    cropped_fig = page_obj.image.image.crop(bbox)
                    fig_path = figures_dir / f"{base_name}_figure_{i+1}.png"
                    cropped_fig.save(fig_path)
        except Exception as e:
            _log.warning(f"Could not export Figure {i+1}: {e}")

# -------------------------------------------------------------------------
# 3. UNSTRUCTURED MAPPING (JSON Schema)
# -------------------------------------------------------------------------
def map_docling_to_unstructured(docling_doc: DoclingDocument) -> List[dict]:
    """Maps Docling structure to Unstructured.io Element objects."""
    unstructured_elements = []

    for item, level in docling_doc.iterate_items():
        metadata = ElementMetadata()
        if hasattr(item, "prov") and item.prov:
            metadata.page_number = item.prov[0].page_no

        if isinstance(item, TableItem):
            html = item.export_to_html(doc=docling_doc)
            csv = item.export_to_dataframe(doc=docling_doc).to_csv(index=False)
            metadata.text_as_html = html
            unstructured_elements.append(Table(text=csv, metadata=metadata))

        elif isinstance(item, SectionHeaderItem):
            unstructured_elements.append(Title(text=item.text, metadata=metadata))

        elif isinstance(item, ListItem):
            unstructured_elements.append(UnstructuredListItem(text=item.text, metadata=metadata))

        elif isinstance(item, TextItem):
            unstructured_elements.append(Text(text=item.text, metadata=metadata))
            
    return unstructured_elements

# -------------------------------------------------------------------------
# 4. MAIN PROCESSING LOGIC
# -------------------------------------------------------------------------
def process_file(file_path: Path, output_root: Path, converter: DocumentConverter, pretty: bool):
    _log.info(f"📄 Processing: {file_path.name}")
    
    try:
        # Create dedicated output folder: output_root/output_filename/
        file_output_dir = output_root / f"output_{file_path.stem}"
        file_output_dir.mkdir(parents=True, exist_ok=True)

        # 1. Convert
        start_time = time.time()
        result = converter.convert(file_path)
        doc = result.document
        _log.info(f"✅ Converted in {time.time() - start_time:.2f}s")

        # 2. Export Standard Formats (Markdown & JSON)
        # Markdown
        md_path = file_output_dir / f"{file_path.stem}.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(doc.export_to_markdown())
        
        # JSON (Unstructured Schema)
        elements = map_docling_to_unstructured(doc)
        json_path = file_output_dir / f"{file_path.stem}.json"
        json_str = elements_to_json(elements, indent=2 if pretty else None)
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(json_str)

        # 3. Export Assets (Visuals)
        _log.info("🖼️  Exporting assets (figures, tables, annotations)...")
        export_assets(doc, file_output_dir, file_path.stem)
        annotate_pages(doc, file_output_dir)

        _log.info(f"🎉 Done! All outputs saved to: {file_output_dir}")

    except Exception as e:
        _log.error(f"❌ Failed to process {file_path.name}: {e}", exc_info=True)

def main():
    p = argparse.ArgumentParser(description="Docling V2: Text, Tables, VLM & Asset Extraction")
    p.add_argument("input", help="File path or glob pattern (e.g., *.pdf)")
    p.add_argument("--out", default="output", help="Root output directory")
    p.add_argument("--vlm", action="store_true", help="Use Granite Docling VLM (Slower, better for complex layouts)")
    p.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    p.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    args = p.parse_args()

    setup_logging(args.verbose)
    
    # Expand file pattern
    files = [Path(f) for f in glob.glob(str(args.input))]
    if not files:
        _log.error(f"No files found for pattern: {args.input}")
        return

    # Initialize Converter ONCE
    converter = get_configured_converter(use_vlm=args.vlm)
    output_root = Path(args.out)

    for file_path in files:
        if file_path.is_file():
            process_file(file_path, output_root, converter, args.pretty)

if __name__ == "__main__":
    main()