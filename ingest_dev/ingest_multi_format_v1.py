#!/usr/bin/env python3
"""
Integrated Docling Extractor v5.5 (Batch + Multi-Format + Robust Filenames + Safety Checks)
Features:
1. Batch Processing: Uses converter.convert_all() for efficiency.
2. Multi-Format: Supports PDF, Images, DOCX, PPTX, HTML, MD.
3. Header Snapping: Automatically expands figures to include the Slide/Section Title.
4. Smart Figure Merging: Reconstructs "Quads" from fragmented detections.
5. Robust Sanitization: Handles trailing spaces and illegal characters in filenames.
6. Pre-Flight Check: Skips files locked by other apps (e.g., PowerPoint) to prevent crashes.
"""
from __future__ import annotations
import argparse
import logging
import time
import re
from pathlib import Path
from typing import List, Tuple

# Data Handling
from PIL import Image

# Docling Core
from docling.document_converter import (
    DocumentConverter, 
    PdfFormatOption, 
    ImageFormatOption, 
    WordFormatOption,
    PowerpointFormatOption,
    HTMLFormatOption
)
from docling.datamodel.base_models import InputFormat, ConversionStatus
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
    ListItem
)
# VLM Support (Optional)
from docling.pipeline.vlm_pipeline import VlmPipeline

# Unstructured Support
from unstructured.documents.elements import Text, Table, Title, ListItem as UnstructuredListItem, ElementMetadata
from unstructured.staging.base import elements_to_json

def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")
    return logging.getLogger(__name__)

_log = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# 1. UTILITIES
# -------------------------------------------------------------------------
def sanitize_filename(name: str) -> str:
    """
    Sanitizes filenames for Windows compatibility.
    1. Removes trailing/leading whitespace.
    2. Removes illegal characters: < > : " / \ | ? *
    """
    name = name.strip()
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    return name

def filter_accessible_files(files: List[Path]) -> List[Path]:
    """
    Pre-checks if files are readable. 
    If a file is open in PowerPoint/Word, Windows locks it, causing a crash.
    This function filters out locked files before processing.
    """
    accessible_files = []
    for f in files:
        try:
            # Try to open the file in read-binary mode to check access
            with open(f, "rb"):
                pass
            accessible_files.append(f)
        except PermissionError:
            _log.warning(f"🚫 SKIPPING LOCKED FILE: '{f.name}'")
            _log.warning(f"   (Action Required: Close this file in PowerPoint/Word and try again)")
        except Exception as e:
            _log.warning(f"🚫 SKIPPING UNREADABLE FILE: '{f.name}' ({e})")
            
    return accessible_files

# -------------------------------------------------------------------------
# 2. PIPELINE CONFIGURATION
# -------------------------------------------------------------------------
def get_configured_converter(use_vlm: bool = False) -> DocumentConverter:
    """
    Configures the converter for multiple formats.
    PDF/Images get OCR/High-Res settings.
    Office docs use standard structural extraction.
    """
    allowed_formats = [
        InputFormat.PDF, InputFormat.IMAGE, 
        InputFormat.DOCX, InputFormat.PPTX, 
        InputFormat.HTML, InputFormat.MD, InputFormat.ASCIIDOC
    ]

    format_options = {}

    if use_vlm:
        _log.info("🚀 Initializing VLM Pipeline (PDF/Image only)...")
        pipeline_options = VlmPipelineOptions()
        format_options[InputFormat.PDF] = PdfFormatOption(pipeline_cls=VlmPipeline, pipeline_options=pipeline_options)
        format_options[InputFormat.IMAGE] = ImageFormatOption(pipeline_cls=VlmPipeline, pipeline_options=pipeline_options)
    else:
        _log.info("🔧 Initializing Standard Pipeline (High-Res PDF/Img, Standard Office)...")
        
        pdf_options = PdfPipelineOptions()
        pdf_options.do_table_structure = True
        pdf_options.table_structure_options.mode = TableFormerMode.ACCURATE
        pdf_options.do_ocr = True
        pdf_options.ocr_options = TesseractCliOcrOptions()
        pdf_options.images_scale = 2.0 
        pdf_options.generate_page_images = True 
        pdf_options.generate_picture_images = True

        format_options[InputFormat.PDF] = PdfFormatOption(pipeline_options=pdf_options)
        format_options[InputFormat.IMAGE] = ImageFormatOption(pipeline_options=pdf_options)
        
        format_options[InputFormat.DOCX] = WordFormatOption()
        format_options[InputFormat.PPTX] = PowerpointFormatOption()
        format_options[InputFormat.HTML] = HTMLFormatOption()

    return DocumentConverter(
        allowed_formats=allowed_formats,
        format_options=format_options
    )

# -------------------------------------------------------------------------
# 3. GEOMETRY & MERGING LOGIC
# -------------------------------------------------------------------------
def merge_nearby_bboxes(bboxes, distance_threshold=50):
    """Merges bounding boxes that are physically close."""
    if not bboxes:
        return []
    
    merged = []
    working_set = list(bboxes)
    
    while working_set:
        current = working_set.pop(0)
        changed = True
        while changed:
            changed = False
            rest = []
            for other in working_set:
                h_overlap = (current[0] <= other[2] + distance_threshold) and (other[0] <= current[2] + distance_threshold)
                v_overlap = (current[1] <= other[3] + distance_threshold) and (other[1] <= current[3] + distance_threshold)
                
                if h_overlap and v_overlap:
                    current = (
                        min(current[0], other[0]),
                        min(current[1], other[1]),
                        max(current[2], other[2]),
                        max(current[3], other[3])
                    )
                    changed = True
                else:
                    rest.append(other)
            working_set = rest
        merged.append(current)
    return merged

def include_header_context(doc: DoclingDocument, page_no: int, bbox: Tuple[float, float, float, float], max_distance: int = 200) -> Tuple[float, float, float, float]:
    """
    Looks for a Section Header above the image bbox and expands the bbox to include it.
    """
    x0, y0, x1, y1 = bbox
    best_header_y = y0
    
    for item in doc.texts:
        if not (hasattr(item, "prov") and item.prov and item.prov[0].page_no == page_no):
            continue
            
        if isinstance(item, SectionHeaderItem) or isinstance(item, TextItem):
            h_bbox = item.prov[0].bbox.as_tuple() # l, t, r, b
            h_x0, h_y0, h_x1, h_y1 = h_bbox
            
            if h_y1 < y0: # It's above
                dist = y0 - h_y1
                if dist < max_distance:
                    if h_y0 < best_header_y:
                        best_header_y = h_y0

    return (x0, best_header_y, x1, y1)

def add_padding(bbox, width, height, padding=15):
    return (
        max(0, bbox[0] - padding),
        max(0, bbox[1] - padding),
        min(width, bbox[2] + padding),
        min(height, bbox[3] + padding)
    )

# -------------------------------------------------------------------------
# 4. ASSET EXPORT
# -------------------------------------------------------------------------
def export_enhanced_assets(doc: DoclingDocument, output_dir: Path, base_name: str):
    tables_dir = output_dir / "tables"
    figures_dir = output_dir / "figures"
    tables_dir.mkdir(exist_ok=True)
    figures_dir.mkdir(exist_ok=True)

    for i, table in enumerate(doc.tables):
        try:
            table.export_to_dataframe(doc).to_csv(tables_dir / f"{base_name}_table_{i+1}.csv", index=False)
        except: pass

    for page_no, page in doc.pages.items():
        if not (page.image and page.image.pil_image):
            continue
            
        full_page_img = page.image.pil_image
        page_w, page_h = full_page_img.size
        
        page_bboxes = []
        for picture in doc.pictures:
            if picture.prov and picture.prov[0].page_no == page_no:
                page_bboxes.append(picture.prov[0].bbox.as_tuple())
        
        merged_bboxes = merge_nearby_bboxes(page_bboxes, distance_threshold=50)
        
        for i, bbox in enumerate(merged_bboxes):
            w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
            if w < 150 or h < 150: continue

            bbox_with_header = include_header_context(doc, page_no, bbox)
            final_bbox = add_padding(bbox_with_header, page_w, page_h, padding=20)
            
            try:
                crop = full_page_img.crop(final_bbox)
                crop.save(figures_dir / f"{base_name}_pg{page_no}_smart_fig_{i+1}.png")
            except Exception as e:
                _log.warning(f"Crop failed on page {page_no}: {e}")

# -------------------------------------------------------------------------
# 5. CONVERSION LOGIC
# -------------------------------------------------------------------------
def map_docling_to_unstructured(docling_doc: DoclingDocument) -> List[dict]:
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

def get_input_files(input_path: str) -> List[Path]:
    path_obj = Path(input_path)
    
    if path_obj.is_dir():
        extensions = ['*.pdf', '*.png', '*.jpg', '*.jpeg', '*.docx', '*.pptx', '*.html', '*.md']
        files = []
        for ext in extensions:
            files.extend(path_obj.rglob(ext))
        return sorted(list(set(files)))
    else:
        import glob
        return [Path(f) for f in glob.glob(input_path)]

def save_result(result, output_root: Path, pretty: bool):
    file_path = result.input.file
    
    if result.status != ConversionStatus.SUCCESS:
        _log.error(f"❌ Conversion failed for: {file_path.name} (Status: {result.status})")
        if result.errors:
            for err in result.errors:
                _log.error(f"   - {err}")
        return

    try:
        clean_stem = sanitize_filename(file_path.stem)
        file_output_dir = output_root / f"output_{clean_stem}"
        file_output_dir.mkdir(parents=True, exist_ok=True)

        doc = result.document
        
        with open(file_output_dir / f"{clean_stem}.md", "w", encoding="utf-8") as f:
            f.write(doc.export_to_markdown())
        
        elements = map_docling_to_unstructured(doc)
        with open(file_output_dir / f"{clean_stem}.json", "w", encoding="utf-8") as f:
            f.write(elements_to_json(elements, indent=2 if pretty else None))

        export_enhanced_assets(doc, file_output_dir, clean_stem)
        
        _log.info(f"✅ Saved: {file_path.name} -> {file_output_dir}")

    except Exception as e:
        _log.error(f"⚠️ Error saving results for {file_path.name}: {e}", exc_info=True)

def main():
    p = argparse.ArgumentParser(description="Docling V5.5: Batch Multi-Format Extractor")
    p.add_argument("input", help="Input directory or file pattern")
    p.add_argument("--out", default="output", help="Output directory")
    p.add_argument("--vlm", action="store_true", help="Use Granite VLM (PDF/Img only)")
    p.add_argument("--pretty", action="store_true", help="Pretty JSON")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    setup_logging(args.verbose)
    
    # 1. Collect Files
    input_files = get_input_files(args.input)
    if not input_files:
        _log.error("No files found matching the input pattern.")
        return
    
    # 2. Check Access (Prevent PermissionError crashes)
    accessible_files = filter_accessible_files(input_files)
    
    if not accessible_files:
        _log.error("No readable files found to process.")
        return

    _log.info(f"📂 Processing {len(accessible_files)} files (skipped {len(input_files) - len(accessible_files)} locked/unreadable files).")

    # 3. Initialize Converter
    converter = get_configured_converter(use_vlm=args.vlm)
    output_root = Path(args.out)

    # 4. Batch Convert
    _log.info("🔄 Starting Batch Conversion...")
    start_time = time.time()
    
    results = converter.convert_all(accessible_files, raises_on_error=False)
    
    for result in results:
        save_result(result, output_root, args.pretty)

    total_time = time.time() - start_time
    _log.info(f"🎉 Batch complete in {total_time:.2f}s")

if __name__ == "__main__":
    main()