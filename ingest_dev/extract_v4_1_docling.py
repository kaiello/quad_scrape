#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "docling",
#     "pandas",
#     "pillow",
#     "unstructured",
# ]
# ///
"""
Integrated Docling Extractor v5 (Windows Compatible + Slide Context)
Features:
1. Header Snapping: Automatically expands figures to include the Slide Title above them.
2. Safety Padding: Adds breathing room around crops so text isn't cut off.
3. Smart Figure Merging: Reconstructs "Quads" from fragmented detections.
4. Artifact Filtering: Ignores small "text box" images.
"""
from __future__ import annotations
import argparse
import logging
import glob
import time
from pathlib import Path
from typing import List, Tuple, Optional

# Data Handling
from PIL import Image

# Docling Core
from docling.document_converter import DocumentConverter, PdfFormatOption, ImageFormatOption
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
)
# VLM Support (Optional)
from docling.pipeline.vlm_pipeline import VlmPipeline

# Unstructured Support
from unstructured.documents.elements import Text, Table, Title, ListItem as UnstructuredListItem, ElementMetadata
from unstructured.staging.base import elements_to_json

# REFACTOR: Constants for magic numbers
MERGE_DISTANCE_THRESHOLD = 50
HEADER_SNAP_DISTANCE = 200
DEFAULT_PADDING = 20
MIN_IMAGE_SIZE_PX = 150

def setup_logging(verbose: bool) -> None:
    """
    Configures the logging level and format.

    Args:
        verbose (bool): If True, sets logging level to DEBUG; otherwise INFO.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

_log = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# 1. PIPELINE CONFIGURATION
# -------------------------------------------------------------------------
def get_configured_converter(use_vlm: bool = False) -> DocumentConverter:
    """
    Initializes the Docling DocumentConverter with specific pipeline options.

    Configures either a VLM-based pipeline or a standard high-resolution PDF pipeline
    with OCR and table structure analysis.

    Args:
        use_vlm (bool): Whether to use the VLM (Vision-Language Model) pipeline.

    Returns:
        DocumentConverter: The configured converter instance.
    """
    if use_vlm:
        _log.info("🚀 Initializing VLM Pipeline...")
        pipeline_options = VlmPipelineOptions()
        return DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_cls=VlmPipeline, pipeline_options=pipeline_options),
                InputFormat.IMAGE: ImageFormatOption(pipeline_cls=VlmPipeline, pipeline_options=pipeline_options)
            }
        )
    else:
        _log.info("🔧 Initializing Standard Pipeline (High-Res)...")
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_table_structure = True
        pipeline_options.table_structure_options.mode = TableFormerMode.ACCURATE
        pipeline_options.do_ocr = True
        pipeline_options.ocr_options = TesseractCliOcrOptions()

        # High Res for better OCR and prettier crops
        pipeline_options.images_scale = 2.0
        pipeline_options.generate_page_images = True
        pipeline_options.generate_picture_images = True

        return DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )

# -------------------------------------------------------------------------
# 2. GEOMETRY & MERGING LOGIC
# -------------------------------------------------------------------------
def merge_nearby_bboxes(
    bboxes: List[Tuple[float, float, float, float]],
    distance_threshold: int = MERGE_DISTANCE_THRESHOLD
) -> List[Tuple[float, float, float, float]]:
    """
    Merges bounding boxes that are physically close.

    Iteratively combines boxes that overlap or are within the `distance_threshold`.
    This helps reconstruct fragmented figures or "quads".

    Args:
        bboxes (List[Tuple[float, float, float, float]]): List of bounding boxes (x0, y0, x1, y1).
        distance_threshold (int): Distance in pixels to consider boxes as nearby.

    Returns:
        List[Tuple[float, float, float, float]]: A list of merged bounding boxes.
    """
    if not bboxes:
        return []

    merged = []
    working_set = list(bboxes)

    while working_set:
        current = working_set.pop(0)
        changed = True
        # REFACTOR: Inner loop ensures we exhaustively merge overlapping boxes with 'current'
        while changed:
            changed = False
            rest = []
            for other in working_set:
                # Check Overlaps/Proximity
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

def include_header_context(
    doc: DoclingDocument,
    page_no: int,
    bbox: Tuple[float, float, float, float],
    max_distance: int = HEADER_SNAP_DISTANCE
) -> Tuple[float, float, float, float]:
    """
    Expands a bounding box upwards to include the nearest section header.

    This provides context (e.g., Slide Title) for images or figures that might
    otherwise be isolated.

    Args:
        doc (DoclingDocument): The parsed document object containing text items.
        page_no (int): The page number (1-based) where the bbox is located.
        bbox (Tuple[float, float, float, float]): The initial bounding box (x0, y0, x1, y1).
        max_distance (int): Maximum vertical distance to search for a header above.

    Returns:
        Tuple[float, float, float, float]: The expanded bounding box including the header if found.
    """
    x0, y0, x1, y1 = bbox
    best_header_y = y0

    # Scan text items for headers on this page
    for item in doc.texts:
        if not (hasattr(item, "prov") and item.prov and item.prov[0].page_no == page_no):
            continue

        # We are interested in Headers or Large Text roughly aligned with the image
        # Docling classifies headers as SectionHeaderItem
        if isinstance(item, SectionHeaderItem) or isinstance(item, TextItem):
            h_bbox = item.prov[0].bbox.as_tuple() # l, t, r, b
            h_x0, h_y0, h_x1, h_y1 = h_bbox

            # Check if it is ABOVE the image
            if h_y1 < y0:
                # Check vertical distance (is it close enough?)
                dist = y0 - h_y1
                if dist < max_distance:
                    # Check horizontal alignment (does it overlap mostly?)
                    # Simple check: is the header roughly in the same vertical column?
                    # We'll be generous: if it's above, we take it.
                    if h_y0 < best_header_y:
                        best_header_y = h_y0
                        _log.info(f"  ↳ Snapped to header: '{item.text[:30]}...'")

    return (x0, best_header_y, x1, y1)

def add_padding(
    bbox: Tuple[float, float, float, float],
    width: int,
    height: int,
    padding: int = 15
) -> Tuple[float, float, float, float]:
    """
    Adds padding to a bounding box, ensuring it stays within image boundaries.

    Args:
        bbox (Tuple[float, float, float, float]): The bounding box (x0, y0, x1, y1).
        width (int): The width of the image/page.
        height (int): The height of the image/page.
        padding (int): The amount of padding in pixels to add on all sides.

    Returns:
        Tuple[float, float, float, float]: The padded bounding box.
    """
    return (
        max(0, bbox[0] - padding),
        max(0, bbox[1] - padding),
        min(width, bbox[2] + padding),
        min(height, bbox[3] + padding)
    )

# -------------------------------------------------------------------------
# 3. ASSET EXPORT
# -------------------------------------------------------------------------
def export_enhanced_assets(doc: DoclingDocument, output_dir: Path, base_name: str) -> None:
    """
    Exports tables as CSVs and figures as cropped images.

    Applies smart merging and header snapping to figures to improve context.

    Args:
        doc (DoclingDocument): The processed Docling document.
        output_dir (Path): Directory where assets should be saved.
        base_name (str): Base filename for the exported assets.
    """
    tables_dir = output_dir / "tables"
    figures_dir = output_dir / "figures"
    tables_dir.mkdir(exist_ok=True)
    figures_dir.mkdir(exist_ok=True)

    # Export Tables
    for i, table in enumerate(doc.tables):
        try:
            table.export_to_dataframe().to_csv(tables_dir / f"{base_name}_table_{i+1}.csv", index=False)
        except Exception as e:
            # REFACTOR: Log specific errors instead of silent fail
            _log.warning(f"Failed to export table {i+1}: {e}")

    # Export Figures (Smart Merge + Header Snap)
    for page_no, page in doc.pages.items():
        if not (page.image and page.image.pil_image):
            continue

        full_page_img = page.image.pil_image
        page_w, page_h = full_page_img.size

        # 1. Collect picture boxes
        page_bboxes = []
        for picture in doc.pictures:
            if picture.prov and picture.prov[0].page_no == page_no:
                page_bboxes.append(picture.prov[0].bbox.as_tuple())

        # 2. Merge "Quad" parts
        merged_bboxes = merge_nearby_bboxes(page_bboxes, distance_threshold=MERGE_DISTANCE_THRESHOLD)

        for i, bbox in enumerate(merged_bboxes):
            w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]

            # Filter artifacts (<150px)
            if w < MIN_IMAGE_SIZE_PX or h < MIN_IMAGE_SIZE_PX: continue

            # 3. ENHANCEMENT: Snap to Header
            # Look for a title above the image to give it context
            bbox_with_header = include_header_context(doc, page_no, bbox, max_distance=HEADER_SNAP_DISTANCE)

            # 4. ENHANCEMENT: Add Padding
            final_bbox = add_padding(bbox_with_header, page_w, page_h, padding=DEFAULT_PADDING)

            try:
                crop = full_page_img.crop(final_bbox)
                crop.save(figures_dir / f"{base_name}_pg{page_no}_smart_fig_{i+1}.png")
                _log.info(f"Saved Smart Figure (with Header): {base_name}_pg{page_no}_smart_fig_{i+1}.png")
            except Exception as e:
                _log.warning(f"Crop failed for figure {i+1} on page {page_no}: {e}")

# -------------------------------------------------------------------------
# 4. MAIN LOGIC
# -------------------------------------------------------------------------
def map_docling_to_unstructured(docling_doc: DoclingDocument) -> List[dict]:
    """
    Maps Docling document structure to Unstructured.io Element objects.

    Iterates through Docling items and converts them to Unstructured equivalents
    (Text, Table, Title, ListItem) with metadata.

    Args:
        docling_doc (DoclingDocument): The source Docling document.

    Returns:
        List[dict]: A list of Unstructured element objects (typically serialized to JSON later).
    """
    unstructured_elements = []
    for item, _ in docling_doc.iterate_items():
        metadata = ElementMetadata()
        if hasattr(item, "prov") and item.prov:
            metadata.page_number = item.prov[0].page_no

        if isinstance(item, TableItem):
            try:
                csv = item.export_to_dataframe(doc=docling_doc).to_csv(index=False)
                html = item.export_to_html(doc=docling_doc)
                metadata.text_as_html = html
                unstructured_elements.append(Table(text=csv, metadata=metadata))
            except Exception as e:
                 # REFACTOR: Log error but continue
                 _log.warning(f"Failed to convert table item to unstructured: {e}")
        elif isinstance(item, SectionHeaderItem):
            unstructured_elements.append(Title(text=item.text, metadata=metadata))
        elif isinstance(item, ListItem):
            unstructured_elements.append(UnstructuredListItem(text=item.text, metadata=metadata))
        elif isinstance(item, TextItem):
            unstructured_elements.append(Text(text=item.text, metadata=metadata))

    return unstructured_elements

def process_file(file_path: Path, output_root: Path, converter: DocumentConverter, pretty: bool) -> None:
    """
    Processes a single file through the Docling pipeline and exports results.

    Converts the document, saves a Markdown export, maps to Unstructured JSON,
    and exports enhanced assets (images, tables).

    Args:
        file_path (Path): Path to the input file.
        output_root (Path): Root directory for output.
        converter (DocumentConverter): Configured Docling converter.
        pretty (bool): Whether to indent the JSON output.
    """
    _log.info(f"📄 Processing: {file_path.name}")
    try:
        file_output_dir = output_root / f"output_{file_path.stem}"
        file_output_dir.mkdir(parents=True, exist_ok=True)

        start_time = time.time()
        result = converter.convert(file_path)
        doc = result.document
        _log.info(f"✅ Converted in {time.time() - start_time:.2f}s")

        # Standard Exports
        with open(file_output_dir / f"{file_path.stem}.md", "w", encoding="utf-8") as f:
            f.write(doc.export_to_markdown())

        elements = map_docling_to_unstructured(doc)
        with open(file_output_dir / f"{file_path.stem}.json", "w", encoding="utf-8") as f:
            f.write(elements_to_json(elements, indent=2 if pretty else None))

        # Enhanced Assets
        _log.info("🖼️  Exporting Enhanced Assets (Smart Merge + Header Snap)...")
        export_enhanced_assets(doc, file_output_dir, file_path.stem)

        _log.info(f"🎉 Done! Saved to: {file_output_dir}")

    except Exception as e:
        _log.error(f"❌ Failed to process {file_path.name}: {e}", exc_info=True)

def main() -> None:
    """
    Main entry point for the Docling extraction script.

    Parses command-line arguments and orchestrates the file processing pipeline.
    """
    p = argparse.ArgumentParser(description="Docling V5: Windows Context-Aware")
    p.add_argument("input", help="File path or glob pattern (e.g., 'data/*.pdf')")
    p.add_argument("--out", default="output", help="Output directory")
    p.add_argument("--vlm", action="store_true", help="Use Granite VLM (Optional)")
    p.add_argument("--pretty", action="store_true", help="Pretty JSON output")
    p.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    args = p.parse_args()

    setup_logging(args.verbose)

    # REFACTOR: Use descriptive variable names
    input_pattern = str(args.input)
    files = [Path(f) for f in glob.glob(input_pattern)]

    if not files:
        _log.warning(f"No files found matching pattern: {input_pattern}")
        return

    converter = get_configured_converter(use_vlm=args.vlm)
    output_root = Path(args.out)

    for file_path in files:
        if file_path.is_file():
            process_file(file_path, output_root, converter, args.pretty)

if __name__ == "__main__":
    main()
