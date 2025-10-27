from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from dataclasses import asdict
from typing import Iterable, List, Optional, Tuple, Dict, Any

from ..io.contracts import ExtractedDoc, Sentence, Chunk


NORMALIZER_NAME = "combo.segment"
NORMALIZER_VERSION = "0.1.0"
SPEC_VERSION = "v1"


def _sha16(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


def _sentence_spans(text: str) -> List[Tuple[int, int]]:
    # Simple, robust sentence segmentation preserving offsets.
    n = len(text)
    spans: List[Tuple[int, int]] = []
    start = 0
    i = 0
    closing = '"\'\u201d\u2019)]'

    def _trim_right(a: int, b: int) -> Tuple[int, int]:
        while b > a and text[b - 1].isspace():
            b -= 1
        while a < b and text[a].isspace():
            a += 1
        return a, b

    while i < n:
        ch = text[i]
        if ch in ".!?":
            end = i + 1
            while end < n and text[end] in closing:
                end += 1
            a, b = _trim_right(start, end)
            if b > a:
                spans.append((a, b))
            # Advance past following whitespace
            j = end
            while j < n and text[j].isspace():
                j += 1
            start = j
            i = j
            continue
        if ch == "\n":
            # Paragraph boundary on blank line
            if i + 1 < n and text[i + 1] == "\n":
                a, b = _trim_right(start, i)
                if b > a:
                    spans.append((a, b))
                j = i + 1
                while j < n and text[j] == "\n":
                    j += 1
                start = j
                i = j
                continue
        i += 1

    # Remainder
    if start < n:
        a, b = _trim_right(start, n)
        if b > a:
            spans.append((a, b))
    return spans


def sentences_for_page(doc_id: str, page_index_1based: Optional[int], page_text: str) -> List[Sentence]:
    sents: List[Sentence] = []
    for a, b in _sentence_spans(page_text):
        sent_text = page_text[a:b]
        sent_id = _sha16(f"{doc_id}|{page_index_1based or ''}|{a}|{b}")
        # Acceptance check: slice equality
        assert sent_text == page_text[a:b]
        sents.append(
            Sentence(
                doc_id=doc_id,
                sent_id=sent_id,
                page=page_index_1based,
                text=sent_text,
                char_start=a,
                char_end=b,
            )
        )
    return sents


def chunk_sentences(doc_id: str, sentences: List[Sentence], max_tokens: int = 512) -> List[Chunk]:
    chunks: List[Chunk] = []
    cur_ids: List[str] = []
    cur_texts: List[str] = []
    cur_pages: List[int] = []
    cur_tokens = 0

    def flush():
        nonlocal cur_ids, cur_texts, cur_pages, cur_tokens
        if not cur_ids:
            return
        first = cur_ids[0]
        last = cur_ids[-1]
        chunk_id = _sha16(f"{doc_id}|{first}|{last}")
        page_start = min(cur_pages) if cur_pages else None
        page_end = max(cur_pages) if cur_pages else None
        chunks.append(
            Chunk(
                doc_id=doc_id,
                chunk_id=chunk_id,
                text=" ".join(cur_texts).strip(),
                sentence_ids=list(cur_ids),
                page_start=page_start,
                page_end=page_end,
            )
        )
        cur_ids, cur_texts, cur_pages, cur_tokens = [], [], [], 0

    for s in sentences:
        toks = len(s.text.split())
        if cur_ids and cur_tokens + toks > max_tokens:
            flush()
        cur_ids.append(s.sent_id)
        cur_texts.append(s.text)
        if s.page is not None:
            cur_pages.append(s.page)
        cur_tokens += toks
    flush()
    return chunks


def to_extracted_doc(item: Dict[str, Any]) -> ExtractedDoc:
    source_path = item.get("source_path") or item.get("path") or item.get("file") or ""
    pages: List[str]
    if isinstance(item.get("pages"), list):
        pages = [p or "" for p in item["pages"]]
    else:
        # Fallback to single text field
        pages = [item.get("text", "")]

    # Normalize images metadata
    imgs_in = item.get("images") or []
    images: List[Dict[str, Any]] = []
    for im in imgs_in:
        if not isinstance(im, dict):
            continue
        keep = {k: im.get(k) for k in ("sha1", "page", "bbox", "saved_path", "ocr_text")}
        images.append(keep)

    return ExtractedDoc(
        doc_id=str(item.get("doc_id") or uuid.uuid4()),
        source_path=source_path,
        pages=pages,
        images=images,
    )


# Convenience helpers for tests and library use
def segment_to_sentences(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    doc = to_extracted_doc(item)
    out: List[Dict[str, Any]] = []
    for idx, page_text in enumerate(doc.pages, start=1):
        page_num: Optional[int] = idx if len(doc.pages) > 1 else 1
        for s in sentences_for_page(doc.doc_id, page_num, page_text or ""):
            out.append(asdict(s))
    return out


def build_chunks(sentences: List[Dict[str, Any]], doc_id: Optional[str] = None, max_tokens: int = 512) -> List[Dict[str, Any]]:
    # Accept dict sentences as produced by segment_to_sentences
    s_objs = [
        Sentence(
            doc_id=s["doc_id"],
            sent_id=s["sent_id"],
            page=s.get("page"),
            text=s["text"],
            char_start=int(s["char_start"]),
            char_end=int(s["char_end"]),
        )
        for s in sentences
    ]
    use_doc_id = doc_id or (s_objs[0].doc_id if s_objs else str(uuid.uuid4()))
    chunks = chunk_sentences(use_doc_id, s_objs, max_tokens=max_tokens)
    return [asdict(c) for c in chunks]


def normalize_item(item: Dict[str, Any]) -> Dict[str, Any]:
    import hashlib

    doc = to_extracted_doc(item)
    all_sents: List[Sentence] = []
    for idx, page_text in enumerate(doc.pages, start=1):
        page_num: Optional[int] = idx if len(doc.pages) > 1 else 1
        all_sents.extend(sentences_for_page(doc.doc_id, page_num, page_text or ""))

    chunks = chunk_sentences(doc.doc_id, all_sents, max_tokens=512)

    doc_sha1 = hashlib.sha1("".join(doc.pages).encode("utf-8")).hexdigest()

    out = {
        "meta": {
            "normalizer": {"name": NORMALIZER_NAME, "version": NORMALIZER_VERSION, "spec": SPEC_VERSION},
            "doc_sha1": doc_sha1,
            "n_sentences": len(all_sents),
            "n_chunks": len(chunks),
        },
        "doc": {
            "doc_id": doc.doc_id,
            "source_path": doc.source_path,
            "num_pages": len(doc.pages),
            "pages": list(doc.pages),
        },
        "sentences": [asdict(s) for s in all_sents],
        "chunks": [asdict(c) for c in chunks],
        "images": doc.images or [],
    }
    return out


def _iter_items_from_json(path: str) -> Iterable[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        for it in data:
            yield it
    else:
        yield data


def _safe_basename_for_item(item: Dict[str, Any], fallback: str) -> str:
    name = (item.get("file") or os.path.basename(item.get("path", "")) or fallback) or "doc"
    base, _ = os.path.splitext(name)
    # Sanitize
    base = "".join(ch for ch in base if ch.isalnum() or ch in ("-", "_")) or "doc"
    return base


def normalize_dir(in_dir: str, out_dir: str) -> List[str]:
    os.makedirs(out_dir, exist_ok=True)
    written: List[str] = []
    for name in os.listdir(in_dir):
        if not name.lower().endswith(".json"):
            continue
        path = os.path.join(in_dir, name)
        idx = 0
        for item in _iter_items_from_json(path):
            idx += 1
            norm = normalize_item(item)
            out_base = _safe_basename_for_item(item, os.path.splitext(name)[0])
            out_name = f"{out_base}.normalized.json" if idx == 1 else f"{out_base}.{idx}.normalized.json"
            out_path = os.path.join(out_dir, out_name)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(norm, f, ensure_ascii=False, sort_keys=True, indent=2)
            written.append(out_path)
    return written


def _resolve(path: str) -> str:
    return os.path.abspath(os.path.realpath(path))


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="combo normalize", description="Build sentences and chunks from extracted JSON")
    p.add_argument("extracted_json_dir", help="Directory containing extracted JSON files")
    p.add_argument("--out", required=True, help="Output directory for normalized JSONs")
    args = p.parse_args(argv)
    try:
        in_dir = _resolve(args.extracted_json_dir)
        out_dir = _resolve(args.out)
        # Forbid writing inside input directory to avoid clobbering
        if out_dir == in_dir or out_dir.startswith(in_dir + os.sep):
            print("Error: --out must not be inside the input directory.")
            return 2
        outs = normalize_dir(in_dir, out_dir)
        print(f"Wrote {len(outs)} files to {out_dir}")
        return 0
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1
