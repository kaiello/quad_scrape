#!/usr/bin/env python3
"""
Universal text extractor for documents with OCR support.

Supported inputs:
- PDF, images (png/jpg/jpeg/tif/tiff/bmp/gif)
- Office Open XML: DOCX, PPTX, XLSX (parsed via zip/xml; no heavy deps)
- CSV (plain text)

OCR backends (auto-detected unless specified):
- Vision Transformer (Hugging Face TrOCR) if transformers+torch available
- Tesseract (pytesseract) if tesseract binary + wrapper available
- EasyOCR if installed

PDF rendering for OCR:
- PyMuPDF (fitz) if available, preferred
- pdf2image + Poppler if available, fallback

This script degrades gracefully and reports missing optional deps.
"""
from __future__ import annotations

import argparse
import io
import os
import sys
import zipfile
import logging
import glob
from dataclasses import dataclass
from typing import List, Optional, Iterable, Tuple
import hashlib

from xml.etree import ElementTree as ET

# Optional imports guarded at runtime
try:
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None  # type: ignore


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


# ----------------------------- OCR Backends -----------------------------

class BaseOCR:
    name = "base"

    def available(self) -> bool:
        return False

    def ocr(self, image: "Image.Image") -> str:
        raise NotImplementedError


class TransformerOCR(BaseOCR):
    name = "transformer"

    def __init__(self, model: Optional[str] = None, device: Optional[int] = None):
        self._pipe = None
        self._error = None
        self._model = model or "microsoft/trocr-base-printed"
        self._device = device

        try:
            from transformers import pipeline  # type: ignore
            kwargs = {"task": "image-to-text", "model": self._model}
            if self._device is not None:
                kwargs["device"] = self._device
            self._pipe = pipeline(**kwargs)
        except Exception as e:  # pragma: no cover
            self._error = e

    def available(self) -> bool:
        return self._pipe is not None

    def ocr(self, image: "Image.Image") -> str:
        if not self.available():
            raise RuntimeError(f"Transformer OCR unavailable: {self._error}")
        try:
            res = self._pipe(image)
            if isinstance(res, list) and res and "generated_text" in res[0]:
                return res[0]["generated_text"].strip()
            if isinstance(res, str):
                return res.strip()
            return str(res)
        except Exception as e:
            logging.debug("Transformer OCR failed: %s", e)
            return ""


class TesseractOCR(BaseOCR):
    name = "tesseract"

    def __init__(self, tesseract_cmd: Optional[str] = None, lang: str = "eng"):
        self._err = None
        self._lang = lang
        self._pytesseract = None
        try:
            import pytesseract  # type: ignore
            if tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            self._pytesseract = pytesseract
        except Exception as e:  # pragma: no cover
            self._err = e

    def available(self) -> bool:
        return self._pytesseract is not None

    def ocr(self, image: "Image.Image") -> str:
        if not self.available():
            raise RuntimeError(f"Tesseract OCR unavailable: {self._err}")
        try:
            return self._pytesseract.image_to_string(image, lang=self._lang)
        except Exception as e:
            logging.debug("Tesseract OCR failed: %s", e)
            return ""


class EasyOCROCR(BaseOCR):
    name = "easyocr"

    def __init__(self, lang: str = "en"):
        self._reader = None
        self._err = None
        self._lang = lang
        try:
            import easyocr  # type: ignore
            self._reader = easyocr.Reader([lang], gpu=False)
        except Exception as e:  # pragma: no cover
            self._err = e

    def available(self) -> bool:
        return self._reader is not None

    def ocr(self, image: "Image.Image") -> str:
        if not self.available():
            raise RuntimeError(f"EasyOCR unavailable: {self._err}")
        try:
            # returns list of (bbox, text, conf)
            result = self._reader.readtext(np_image_from_pil(image))
            return "\n".join([t for _, t, _ in result])
        except Exception as e:
            logging.debug("EasyOCR failed: %s", e)
            return ""


def np_image_from_pil(img: "Image.Image"):
    try:
        import numpy as np  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError("NumPy is required for EasyOCR backend") from e
    return np.array(img.convert("RGB"))


def choose_ocr_backend(preferred: str = "auto") -> BaseOCR:
    preferred = preferred.lower()
    tess_cmd = os.environ.get("TESSERACT_CMD")

    # Use factories to avoid heavy imports/initialization (e.g., EasyOCR) unless needed
    def f_transformer():
        return TransformerOCR()

    def f_tesseract():
        return TesseractOCR(tesseract_cmd=tess_cmd)

    def f_easyocr():
        return EasyOCROCR()

    if preferred == "transformer":
        factories = [f_transformer, f_tesseract, f_easyocr]
    elif preferred == "tesseract":
        factories = [f_tesseract, f_transformer, f_easyocr]
    elif preferred == "easyocr":
        factories = [f_easyocr, f_transformer, f_tesseract]
    else:
        factories = [f_transformer, f_tesseract, f_easyocr]

    tried: List[str] = []
    for make in factories:
        try:
            backend = make()
            tried.append(getattr(backend, 'name', str(backend)))
            if backend.available():
                logging.info("Using OCR backend: %s", backend.name)
                return backend
        except Exception as e:
            logging.debug("OCR backend init failed: %s", e)
            continue
    raise RuntimeError(
        f"No OCR backend available. Tried: {', '.join(tried)}. Install transformers+torch or pytesseract+tesseract or easyocr."
    )


def _ocr_tiled(image: "Image.Image", backend: BaseOCR, tiles_x: int = 3, tiles_y: int = 4) -> str:
    """Run OCR over a grid of tiles and join results.
    Useful for transformer OCR which performs better on smaller text regions.
    """
    try:
        w, h = image.size
        tile_w = max(1, w // tiles_x)
        tile_h = max(1, h // tiles_y)
        texts: List[str] = []
        for ty in range(tiles_y):
            row_parts: List[str] = []
            for tx in range(tiles_x):
                left = tx * tile_w
                upper = ty * tile_h
                right = w if tx == tiles_x - 1 else (tx + 1) * tile_w
                lower = h if ty == tiles_y - 1 else (ty + 1) * tile_h
                crop = image.crop((left, upper, right, lower))
                try:
                    txt = backend.ocr(crop).strip()
                except Exception:
                    txt = ""
                if txt:
                    row_parts.append(txt)
            if row_parts:
                texts.append(" \n".join(row_parts))
        return "\n\n".join(texts).strip()
    except Exception:
        return ""


# --------------------------- Office: DOCX/PPTX --------------------------

def extract_docx_text(path: str) -> str:
    with zipfile.ZipFile(path) as z:
        parts = []
        # Main document
        for key in [
            "word/document.xml",
            "word/header1.xml",
            "word/header2.xml",
            "word/header3.xml",
            "word/footer1.xml",
            "word/footer2.xml",
            "word/footer3.xml",
        ]:
            if key in z.namelist():
                xml = z.read(key)
                parts.append(_extract_docx_xml_text(xml))
        return "\n".join(p for p in parts if p)


def _extract_docx_xml_text(xml_bytes: bytes) -> str:
    ns = {
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    }
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return ""
    texts = []
    for t in root.findall('.//w:t', ns):
        if t.text:
            texts.append(t.text)
    # Paragraph breaks
    para_breaks = len(root.findall('.//w:p', ns))
    text = "".join(texts)
    # Roughly insert newlines between paragraphs when possible
    if para_breaks and text and not text.endswith("\n"):
        text += "\n"
    return text


def extract_pptx_text(path: str) -> str:
    with zipfile.ZipFile(path) as z:
        slide_paths = sorted([n for n in z.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")])
        notes_paths = sorted([n for n in z.namelist() if n.startswith("ppt/notesSlides/notesSlide") and n.endswith(".xml")])
        parts = []
        for sp in slide_paths:
            xml = z.read(sp)
            txt = _extract_pptx_xml_text(xml)
            parts.append(f"--- Slide {len(parts)+1} ---\n{txt}\n")
        for npth in notes_paths:
            xml = z.read(npth)
            txt = _extract_pptx_xml_text(xml)
            parts.append(f"--- Notes {npth} ---\n{txt}\n")
        return "\n".join(p for p in parts if p)


def _extract_pptx_xml_text(xml_bytes: bytes) -> str:
    ns = {
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
        "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    }
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return ""

    paragraphs: List[str] = []
    # Iterate by paragraph to avoid splitting every run on a new line
    for p_node in root.findall('.//a:p', ns):
        parts: List[str] = []
        # runs inside a paragraph
        for child in list(p_node):
            tag = child.tag
            # handle run: a:r/a:t
            if tag.endswith('}r'):
                t = child.find('a:t', ns)
                if t is not None and t.text:
                    parts.append(t.text)
            # handle explicit line breaks inside paragraph
            elif tag.endswith('}br'):
                parts.append("\n")
        para = "".join(parts).strip()
        if para:
            paragraphs.append(para)

    # Fallback: if no paragraphs found, join plain text runs as a line
    if not paragraphs:
        texts = []
        for t in root.findall('.//a:t', ns):
            if t.text:
                texts.append(t.text)
        return " ".join(texts)

    return "\n".join(paragraphs)


# --------------------------- Office: XLSX/CSV ---------------------------

def extract_csv_text(path: str, encoding: str = "utf-8-sig") -> str:
    import csv
    out_lines: List[str] = []
    with open(path, "r", encoding=encoding, errors="replace", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            out_lines.append("\t".join(row))
    return "\n".join(out_lines)


def extract_xlsx_text(path: str) -> str:
    with zipfile.ZipFile(path) as z:
        shared_strings = _xlsx_shared_strings(z)
        sheet_paths = sorted([n for n in z.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")])
        parts: List[str] = []
        for idx, sp in enumerate(sheet_paths, start=1):
            xml = z.read(sp)
            text = _xlsx_sheet_text(xml, shared_strings)
            if text.strip():
                parts.append(f"--- Sheet {idx} ---\n{text}")
        return "\n\n".join(parts)


def _xlsx_shared_strings(z: zipfile.ZipFile) -> List[str]:
    try:
        xml = z.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    strings: List[str] = []
    for si in root.findall(".//s:si", ns):
        # A shared string can have multiple runs (r/t)
        text_parts = []
        for t in si.findall('.//s:t', ns):
            if t.text:
                text_parts.append(t.text)
        strings.append("".join(text_parts))
    return strings


def _xlsx_sheet_text(xml_bytes: bytes, shared_strings: List[str]) -> str:
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return ""
    lines: List[str] = []
    for row in root.findall('.//s:sheetData/s:row', ns):
        cells = []
        for c in row.findall('s:c', ns):
            t = c.get('t')  # type of cell
            v = c.find('s:v', ns)
            is_node = c.find('s:is', ns)
            text = ""
            if t == 's' and v is not None and v.text is not None:
                # shared string
                try:
                    idx = int(v.text)
                    text = shared_strings[idx] if 0 <= idx < len(shared_strings) else ""
                except Exception:
                    text = v.text
            elif is_node is not None:
                # inline string
                ts = [t.text for t in is_node.findall('.//s:t', ns) if t.text]
                text = "".join(ts)
            elif v is not None and v.text is not None:
                text = v.text
            cells.append(text)
        lines.append("\t".join(cells))
    return "\n".join(lines)


# ------------------------------- PDF/Image ------------------------------

def extract_pdf_text(path: str, ocr_backend: Optional[BaseOCR] = None, dpi: int = 200, max_pages: Optional[int] = None) -> str:
    text_parts: List[str] = []

    # Try PyMuPDF first for embedded text and rendering
    try:
        import fitz  # type: ignore
        doc = fitz.open(path)
        for i, page in enumerate(doc):
            if max_pages is not None and i >= max_pages:
                break
            try:
                txt = page.get_text("text")
            except Exception:
                txt = ""
            if txt and len(txt.strip()) >= 10:
                text_parts.append(txt)
            else:
                if ocr_backend is None:
                    continue
                # render page to image
                pix = page.get_pixmap(dpi=dpi)
                if Image is None:
                    continue
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                text_parts.append(ocr_backend.ocr(img))
        doc.close()
        return "\n".join(t for t in text_parts if t)
    except Exception as e:
        logging.debug("PyMuPDF unavailable or failed: %s", e)

    # Fallback: pypdf for embedded text
    try:
        from pypdf import PdfReader  # type: ignore
        reader = PdfReader(path)
        for i, page in enumerate(reader.pages):
            if max_pages is not None and i >= max_pages:
                break
            try:
                txt = page.extract_text() or ""
            except Exception:
                txt = ""
            if txt.strip() and len(txt.strip()) >= 10:
                text_parts.append(txt)
        if text_parts:
            return "\n".join(text_parts)
    except Exception as e:
        logging.debug("pypdf unavailable or failed: %s", e)

    # Fallback: rasterize via pdf2image if present, then OCR
    if ocr_backend is not None:
        try:
            from pdf2image import convert_from_path  # type: ignore
            images = convert_from_path(path, dpi=dpi)
            if max_pages is not None:
                images = images[:max_pages]
            for img in images:
                text_parts.append(ocr_backend.ocr(img))
            return "\n".join(t for t in text_parts if t)
        except Exception as e:
            logging.debug("pdf2image unavailable or failed: %s", e)

    logging.warning("Could not extract text from PDF: missing PDF engine and/or OCR backend.")
    return ""


def extract_image_text(path: str, ocr_backend: BaseOCR) -> str:
    if Image is None:
        raise RuntimeError("Pillow is required for image OCR.")
    with Image.open(path) as img:
        img = img.convert("RGB")
        return ocr_backend.ocr(img)


# --------------------------- Dispatcher / CLI ---------------------------

OFFICE_DOC_EXTS = {".docx"}
OFFICE_PPT_EXTS = {".pptx"}
OFFICE_XLS_EXTS = {".xlsx"}
CSV_EXTS = {".csv"}
PDF_EXTS = {".pdf"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif"}


def extract_any(path: str, backend_preference: str = "auto", dpi: int = 200, max_pages: Optional[int] = None) -> str:
    ext = os.path.splitext(path)[1].lower()
    logging.info("Extracting from: %s", path)

    if ext in CSV_EXTS:
        return extract_csv_text(path)

    if ext in OFFICE_XLS_EXTS:
        return extract_xlsx_text(path)

    if ext in OFFICE_DOC_EXTS:
        return extract_docx_text(path)

    if ext in OFFICE_PPT_EXTS:
        return extract_pptx_text(path)

    if ext in IMAGE_EXTS:
        ocr = choose_ocr_backend(backend_preference)
        return extract_image_text(path, ocr)

    if ext in PDF_EXTS:
        # Try to extract embedded text; if none, OCR
        try:
            ocr = choose_ocr_backend(backend_preference)
        except Exception:
            ocr = None
        return extract_pdf_text(path, ocr_backend=ocr, dpi=dpi, max_pages=max_pages)

    raise ValueError(f"Unsupported file type: {ext}")


# ------------------------------ Image Export ------------------------------

def _save_image_bytes(img_bytes: bytes, fmt: str, export_dir: Optional[str], base_name: str) -> Optional[str]:
    if not export_dir:
        return None
    os.makedirs(export_dir, exist_ok=True)
    ext = fmt.lower()
    if not ext.startswith('.'):
        ext = f'.{ext}'
    out_path = os.path.join(export_dir, f"{base_name}{ext}")
    # Avoid overwrite collisions
    idx = 1
    base_out = os.path.splitext(out_path)[0]
    while os.path.exists(out_path):
        out_path = f"{base_out}_{idx}{ext}"
        idx += 1
    with open(out_path, 'wb') as f:
        f.write(img_bytes)
    return out_path


def _ocr_image_bytes(img_bytes: bytes, ocr_backend: Optional[BaseOCR]) -> str:
    if ocr_backend is None or Image is None:
        return ""
    try:
        from PIL import Image as _PILImage
        img = _PILImage.open(io.BytesIO(img_bytes)).convert("RGB")
        return ocr_backend.ocr(img)
    except Exception as e:
        logging.debug("OCR image bytes failed: %s", e)
        return ""


def collect_images_metadata(path: str, export_dir: Optional[str], backend_preference: str = "auto", dpi: int = 200, do_ocr: bool = True) -> List[dict]:
    ext = os.path.splitext(path)[1].lower()
    images_meta: List[dict] = []
    # Try to choose OCR backend but keep optional
    ocr = None
    if do_ocr:
        try:
            ocr = choose_ocr_backend(backend_preference)
        except Exception:
            ocr = None

    if ext in OFFICE_DOC_EXTS:
        # DOCX images under word/media/*
        try:
            with zipfile.ZipFile(path) as z:
                file_base = os.path.splitext(os.path.basename(path))[0]
                counter = 0
                for name in z.namelist():
                    img_ext = os.path.splitext(name)[1].lower()
                    if name.startswith('word/media/') and img_ext in IMAGE_EXTS:
                        data = z.read(name)
                        # Prefer numeric suffix from source filename (e.g., image3.jpg)
                        src_base = os.path.splitext(os.path.basename(name))[0]
                        digits = ''.join([c for c in src_base if c.isdigit()])
                        if digits:
                            idx = digits
                        else:
                            counter += 1
                            idx = str(counter)
                        base_name = f"{file_base}_doc_image{idx}"
                        out_path = _save_image_bytes(data, img_ext, export_dir, base_name)
                        ocr_text = _ocr_image_bytes(data, ocr) if do_ocr else ""
                        sha1 = hashlib.sha1(data).hexdigest()
                        images_meta.append({
                            "source": name,
                            "format": img_ext.lstrip('.'),
                            "saved_path": out_path,
                            "sha1": sha1,
                            "ocr_text": ocr_text,
                        })
        except Exception as e:
            logging.debug("DOCX image extraction failed: %s", e)
        return images_meta

    if ext in OFFICE_PPT_EXTS:
        # PPTX images under ppt/media/*
        try:
            with zipfile.ZipFile(path) as z:
                file_base = os.path.splitext(os.path.basename(path))[0]
                counter = 0
                for name in z.namelist():
                    img_ext = os.path.splitext(name)[1].lower()
                    if name.startswith('ppt/media/') and img_ext in IMAGE_EXTS:
                        data = z.read(name)
                        # Prefer numeric suffix from source filename (e.g., image1.jpg)
                        src_base = os.path.splitext(os.path.basename(name))[0]
                        digits = ''.join([c for c in src_base if c.isdigit()])
                        if digits:
                            idx = digits
                        else:
                            counter += 1
                            idx = str(counter)
                        base_name = f"{file_base}_ppt_image{idx}"
                        out_path = _save_image_bytes(data, img_ext, export_dir, base_name)
                        ocr_text = _ocr_image_bytes(data, ocr) if do_ocr else ""
                        sha1 = hashlib.sha1(data).hexdigest()
                        images_meta.append({
                            "source": name,
                            "format": img_ext.lstrip('.'),
                            "saved_path": out_path,
                            "sha1": sha1,
                            "ocr_text": ocr_text,
                        })
        except Exception as e:
            logging.debug("PPTX image extraction failed: %s", e)
        return images_meta

    if ext in PDF_EXTS:
        # Use PyMuPDF for placed images only (image blocks), not all resources
        try:
            import fitz  # type: ignore
            doc = fitz.open(path)
            for page_index, page in enumerate(doc):
                used_xrefs = set()
                try:
                    pdict = page.get_text("rawdict")
                    blocks = pdict.get("blocks", []) if isinstance(pdict, dict) else []
                except Exception:
                    blocks = []
                # Collect xrefs from image blocks so we only export images actually on the page
                for blk in blocks:
                    if blk.get("type") == 1:  # image block
                        xref = blk.get("image")
                        bbox = blk.get("bbox")
                        if xref is not None:
                            used_xrefs.add((xref, tuple(bbox) if bbox else None))
                # Fallback: if no image blocks detected, collect all images on page
                if not used_xrefs:
                    try:
                        for img in page.get_images(full=True):
                            xref = img[0]
                            used_xrefs.add((xref, None))
                    except Exception:
                        pass
                img_counter = 0
                for xref, bbox in used_xrefs:
                    try:
                        base = doc.extract_image(xref)
                        img_bytes = base.get('image')
                        fmt = base.get('ext', 'png')
                        width = base.get('width')
                        height = base.get('height')
                        img_counter += 1
                        file_base = os.path.splitext(os.path.basename(path))[0]
                        base_name = f"{file_base}_pdf_p{page_index+1}_image{img_counter}"
                        out_path = _save_image_bytes(img_bytes, fmt, export_dir, base_name) if img_bytes else None
                        ocr_text = _ocr_image_bytes(img_bytes, ocr) if (img_bytes and do_ocr) else ""
                        sha1 = hashlib.sha1(img_bytes).hexdigest() if img_bytes else None
                        meta = {
                            "page": page_index + 1,
                            "format": fmt,
                            "width": width,
                            "height": height,
                            "saved_path": out_path,
                            "sha1": sha1,
                            "ocr_text": ocr_text,
                        }
                        if bbox:
                            # bbox: [x0, y0, x1, y1]
                            meta["bbox"] = bbox
                        images_meta.append(meta)
                    except Exception as e:
                        logging.debug("PDF image extract failed (xref=%s): %s", xref, e)
            doc.close()
        except Exception as e:
            logging.debug("PyMuPDF image extraction unavailable: %s", e)
        return images_meta

    if ext in IMAGE_EXTS:
        # Single image file; include as images metadata as well
        try:
            with open(path, 'rb') as f:
                data = f.read()
            fmt = ext.lstrip('.')
            out_path = _save_image_bytes(data, fmt, export_dir, os.path.basename(path))
            ocr_text = _ocr_image_bytes(data, ocr) if do_ocr else ""
            sha1 = hashlib.sha1(data).hexdigest()
            try:
                if Image is not None:
                    with Image.open(io.BytesIO(data)) as im:
                        width, height = im.size
                else:
                    width = height = None
            except Exception:
                width = height = None
            images_meta.append({
                "format": fmt,
                "width": width,
                "height": height,
                "saved_path": out_path,
                "sha1": sha1,
                "ocr_text": ocr_text,
            })
        except Exception as e:
            logging.debug("Image file metadata failed: %s", e)
        return images_meta

    return images_meta


def write_output(text: str, out_path: Optional[str]) -> None:
    if out_path:
        # Ensure parent directory exists
        parent = os.path.dirname(os.path.abspath(out_path)) or "."
        os.makedirs(parent, exist_ok=True)
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        logging.info("Wrote output: %s", out_path)
    else:
        try:
            # Prefer UTF-8 on capable terminals (Windows may default to cp1252)
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8")
            sys.stdout.write(text)
        except UnicodeEncodeError:
            # Fallback to raw bytes with UTF-8
            sys.stdout.buffer.write(text.encode("utf-8", errors="replace"))


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extract text from docs with OCR (optionally using vision transformers)")
    p.add_argument("input", help="Path to a file or glob (e.g. *.pdf)")
    p.add_argument("--backend", choices=["auto", "transformer", "tesseract", "easyocr"], default="auto", help="OCR backend preference")
    p.add_argument("--dpi", type=int, default=200, help="Rasterization DPI for PDF OCR")
    p.add_argument("--min-text-chars", type=int, default=10, help="If embedded PDF text per page is shorter than this, OCR the page")
    p.add_argument("--max-pages", type=int, default=None, help="Limit number of pages for PDFs")
    p.add_argument("--out", default=None, help="Write output to file (for multiple inputs, suffix with .txt next to each)")
    p.add_argument("--format", choices=["txt", "json"], default="txt", help="Output format")
    p.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    p.add_argument("--export-images", default=None, help="Directory to export embedded images (and include metadata in JSON)")
    p.add_argument("--no-image-ocr", action="store_true", help="Do not OCR embedded images when exporting metadata")
    p.add_argument("--force-ocr-pages", action="store_true", help="Force OCR for PDF pages even if embedded text exists")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args(argv)


def _extract_pdf_pages_for_json(path: str, backend_pref: str, dpi: int, max_pages: Optional[int], force_ocr: bool = False):
    try:
        ocr = None
        try:
            ocr = choose_ocr_backend(backend_pref)
        except Exception:
            ocr = None

        pages: List[str] = []
        # Try PyMuPDF for pages
        try:
            import fitz  # type: ignore
            from PIL import Image as _PILImage  # ensure pillow is present when rendering
            doc = fitz.open(path)
            for i, page in enumerate(doc):
                if max_pages is not None and i >= max_pages:
                    break
                txt = ""
                try:
                    txt = page.get_text("text") or ""
                except Exception:
                    txt = ""
                if (force_ocr or len((txt or "").strip()) < 10) and ocr is not None and Image is not None:
                    pix = page.get_pixmap(dpi=dpi)
                    img = _PILImage.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    # For transformer OCR, try tiling to improve results on multi-line pages
                    try:
                        backend_name = getattr(ocr, 'name', '')
                    except Exception:
                        backend_name = ''
                    if backend_name == 'transformer':
                        res = ocr.ocr(img)
                        # If very short, try tiled OCR
                        if len((res or '').strip()) < 30:
                            tiled = _ocr_tiled(img, ocr)
                            txt = tiled if tiled else res
                        else:
                            txt = res
                    else:
                        txt = ocr.ocr(img)
                pages.append(txt)
            doc.close()
            return pages
        except Exception:
            pass

        # Fallback pypdf (embedded text only)
        try:
            from pypdf import PdfReader  # type: ignore
            reader = PdfReader(path)
            for i, page in enumerate(reader.pages):
                if max_pages is not None and i >= max_pages:
                    break
                try:
                    pages.append(page.extract_text() or "")
                except Exception:
                    pages.append("")
            if pages:
                return pages
        except Exception:
            pass

        # pdf2image rasterization + OCR
        if ocr is not None:
            try:
                from pdf2image import convert_from_path  # type: ignore
                images = convert_from_path(path, dpi=dpi)
                if max_pages is not None:
                    images = images[:max_pages]
                for img in images:
                    pages.append(ocr.ocr(img))
                return pages
            except Exception:
                pass
    except Exception:
        pass
    return []


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    setup_logging(args.verbose)

    matches = glob.glob(args.input)
    if not matches and os.path.exists(args.input):
        matches = [args.input]

    if not matches:
        logging.error("No files matched: %s", args.input)
        return 2

    multi = len(matches) > 1

    if args.format == "json":
        import json
        results = []
        for path in matches:
            try:
                ext = os.path.splitext(path)[1].lower()
                item = {"file": os.path.basename(path), "path": path, "type": ext.lstrip('.')}
                if ext in PDF_EXTS:
                    pages = _extract_pdf_pages_for_json(path, args.backend, args.dpi, args.max_pages, force_ocr=args.force_ocr_pages)
                    item["pages"] = pages
                    item["text"] = "\n".join(pages)
                    imgs = collect_images_metadata(path, args.export_images, backend_preference=args.backend, dpi=args.dpi, do_ocr=not args.no_image_ocr)
                    if imgs:
                        item["images"] = imgs
                else:
                    text = extract_any(path, backend_preference=args.backend, dpi=args.dpi, max_pages=args.max_pages)
                    item["text"] = text
                    imgs = collect_images_metadata(path, args.export_images, backend_preference=args.backend, dpi=args.dpi, do_ocr=not args.no_image_ocr)
                    if imgs:
                        item["images"] = imgs
                results.append(item)
            except Exception as e:
                logging.error("Failed to extract %s: %s", path, e)
        payload = results[0] if not multi else results
        text = json.dumps(payload, indent=2 if args.pretty else None, ensure_ascii=False)
        write_output(text, args.out)
        return 0

    # default txt path
    all_text_parts: List[str] = []
    per_file_output_dir: Optional[str] = args.out if (args.out and os.path.isdir(args.out)) else None
    for path in matches:
        try:
            text = extract_any(path, backend_preference=args.backend, dpi=args.dpi, max_pages=args.max_pages)
            if per_file_output_dir:
                base = os.path.basename(path)
                out_name = f"{base}.txt"
                out_path = os.path.join(per_file_output_dir, out_name)
                write_output(text, out_path)
            else:
                all_text_parts.append(f"===== {os.path.basename(path)} =====\n{text}\n")
        except Exception as e:
            logging.error("Failed to extract %s: %s", path, e)

    if not multi:
        write_output(all_text_parts[0] if all_text_parts else "", args.out)
    else:
        if not args.out or not per_file_output_dir:
            # Write aggregated to specified file (if provided and not a directory) or stdout
            write_output("\n\n".join(all_text_parts), args.out if args.out and not per_file_output_dir else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
