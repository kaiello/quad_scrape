#!/usr/bin/env python3
"""
Integrated Docling Extractor v3 (Quad-Optimized)
Features:
1. Smart Figure Merging: Reconstructs "Quads" from fragmented detections.
2. Artifact Filtering: Ignores small "text box" images.
3. High-Res Processing: Increases image scale for better detection.
4. Standard + VLM Support.
"""
from __future__ import annotations
import argparse
import logging
import glob
import time
from pathlib import Path
from typing import List

# Data Handling
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

def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")
    return logging.getLogger(__name__)

_log = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# 1. PIPELINE CONFIGURATION (Optimized)
# -------------------------------------------------------------------------
def get_configured_converter(use_vlm: bool = False) -> DocumentConverter:
    if use_vlm:
        _log.info("🚀 Initializing VLM Pipeline (Granite Docling)...")
        pipeline_options = VlmPipelineOptions(
            vlm_options=vlm_model_specs.GRANITEDOCLING_MLX 
        )
        # VLM already handles visuals well, but we enforce high res
        pipeline_options.images_scale = 2.0 
        
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
        _log.info("🔧 Initializing Standard Pipeline (High-Res)...")
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_table_structure = True
        pipeline_options.table_structure_options.mode = TableFormerMode.ACCURATE
        pipeline_options.do_ocr = True
        pipeline_options.ocr_options = TesseractCliOcrOptions()
        
        # OPTIMIZATION 1: Increase Image Scale (Default is 1.0)
        # Setting to 2.0 (144 DPI) helps the model see boundaries of Quads better
        pipeline_options.images_scale = 2.0 
        pipeline_options.generate_page_images = True 
        pipeline_options.generate_picture_images = True

        return DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )

# -------------------------------------------------------------------------
# 2. SMART ASSET EXTRACTION (The "Quad" Fix)
# -------------------------------------------------------------------------
def merge_nearby_bboxes(bboxes, distance_threshold=50):
    """
    Merges bounding boxes that are close to each other. 
    Useful for reconstructing Quads that were split into 4 parts.
    """
    if not bboxes:
        return []

    # Convert to [x0, y0, x1, y1] format for easier math
    # Docling bbox is usually (l, b, r, t) or similar. 
    # We assume standard PIL coordinates here (left, top, right, bottom)
    
    merged = []
    while bboxes:
        # Start with the first box
        current = bboxes.pop(0)
        changed = True
        
        while changed:
            changed = False
            rest = []
            for other in bboxes:
                # Check distance
                # Horizontal overlap or close?
                h_overlap = (current[0] <= other[2] + distance_threshold) and (other[0] <= current[2] + distance_threshold)
                # Vertical overlap or close?
                v_overlap = (current[1] <= other[3] + distance_threshold) and (other[1] <= current[3] + distance_threshold)
                
                if h_overlap and v_overlap:
                    # Merge
                    current = (
                        min(current[0], other[0]),
                        min(current[1], other[1]),
                        max(current[2], other[2]),
                        max(current[3], other[3])
                    )
                    changed = True
                else:
                    rest.append(other)
            bboxes = rest
        merged.append(current)
        
    return merged

def export_smart_assets(doc: DoclingDocument, output_dir: Path, base_name: str, min_size: int = 200):
    """
    Exports merged figures and filters out small artifacts.
    """
    tables_dir = output_dir / "tables"
    figures_dir = output_dir / "figures"
    tables_dir.mkdir(exist_ok=True)
    figures_dir.mkdir(exist_ok=True)

    # --- Export Tables ---
    for i, table in enumerate(doc.tables):
        try:
            table_df = table.export_to_dataframe()
            csv_path = tables_dir / f"{base_name}_table_{i+1}.csv"
            table_df.to_csv(csv_path, index=False)
        except Exception:
            pass

    # --- Export Figures (With Merging & Filtering) ---
    for page_no, page in doc.pages.items():
        if not (page.image and page.image.pil_image):
            continue
            
        full_page_img = page.image.pil_image
        
        # 1. Collect all picture bboxes on this page
        page_bboxes = []
        for picture in doc.pictures:
            if picture.prov and picture.prov[0].page_no == page_no:
                bbox = picture.prov[0].bbox.as_tuple() # (L, T, R, B)
                page_bboxes.append(bbox)
        
        # 2. Merge close boxes (Reconstruct the Quad)
        merged_bboxes = merge_nearby_bboxes(page_bboxes, distance_threshold=50) # 50px gap tolerance
        
        # 3. Export Merged Figures
        for i, bbox in enumerate(merged_bboxes):
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            
            # OPTIMIZATION 2: Filter Small Artifacts (Text boxes detected as images)
            if w < min_size or h < min_size:
                _log.info(f"Skipping small artifact on pg{page_no} ({int(w)}x{int(h)})")
                continue
                
            try:
                cropped_fig = full_page_img.crop(bbox)
                fig_path = figures_dir / f"{base_name}_pg{page_no}_merged_figure_{i+1}.png"
                cropped_fig.save(fig_path)
                _log.info(f"Saved Smart-Merged Figure: {fig_path.name}")
            except Exception as e:
                _log.warning(f"Failed to save figure: {e}")

def map_docling_to_unstructured(docling_doc: DoclingDocument) -> List[dict]:
    """Maps Docling structure to Unstructured.io Element objects."""
    unstructured_elements = []
    for item, level in docling_doc.iterate_items():
        metadata = ElementMetadata()
        if hasattr(item, "prov") and item.prov:
            metadata.page_number = item.prov[0].page_no

        if isinstance(item, TableItem):
            try:
                csv = item.export_to_dataframe(doc=docling_doc).to_csv(index=False)
                html = item.export_to_html(doc=docling_doc)
                metadata.text_as_html = html
                unstructured_elements.append(Table(text=csv, metadata=metadata))
            except: pass
        elif isinstance(item, SectionHeaderItem):
            unstructured_elements.append(Title(text=item.text, metadata=metadata))
        elif isinstance(item, ListItem):
            unstructured_elements.append(UnstructuredListItem(text=item.text, metadata=metadata))
        elif isinstance(item, TextItem):
            unstructured_elements.append(Text(text=item.text, metadata=metadata))
            
    return unstructured_elements

def process_file(file_path: Path, output_root: Path, converter: DocumentConverter, pretty: bool):
    _log.info(f"📄 Processing: {file_path.name}")
    try:
        file_output_dir = output_root / f"output_{file_path.stem}"
        file_output_dir.mkdir(parents=True, exist_ok=True)

        # 1. Convert
        start_time = time.time()
        result = converter.convert(file_path)
        doc = result.document
        _log.info(f"✅ Converted in {time.time() - start_time:.2f}s")

        # 2. Exports
        md_path = file_output_dir / f"{file_path.stem}.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(doc.export_to_markdown())
        
        elements = map_docling_to_unstructured(doc)
        json_path = file_output_dir / f"{file_path.stem}.json"
        json_str = elements_to_json(elements, indent=2 if pretty else None)
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(json_str)

        # 3. Smart Assets
        _log.info("🖼️  Running Smart Asset Extraction (Merging & Filtering)...")
        export_smart_assets(doc, file_output_dir, file_path.stem, min_size=150) # Ignore imgs < 150px

        _log.info(f"🎉 Done! Saved to: {file_output_dir}")

    except Exception as e:
        _log.error(f"❌ Failed: {e}", exc_info=True)

def main():
    p = argparse.ArgumentParser(description="Docling V3: Quad Optimized")
    p.add_argument("input", help="File path or glob")
    p.add_argument("--out", default="output", help="Output dir")
    p.add_argument("--vlm", action="store_true", help="Use Granite VLM (Recommended for Visuals)")
    p.add_argument("--pretty", action="store_true", help="Pretty JSON")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    setup_logging(args.verbose)
    files = [Path(f) for f in glob.glob(str(args.input))]
    
    converter = get_configured_converter(use_vlm=args.vlm)
    output_root = Path(args.out)

    for file_path in files:
        if file_path.is_file():
            process_file(file_path, output_root, converter, args.pretty)

if __name__ == "__main__":
    main()