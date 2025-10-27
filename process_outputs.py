#!/usr/bin/env python3
"""
Post-process extracted text:
- Lowercase everything
- Remove basic stopwords and punctuation
- Run NER
- Lemmatize all non-entity tokens; keep entity surface forms for selected types

Input formats supported:
- JSON from extract_text_ocr.py (single object or array). Uses the "text" field.
- Plain text files

Output:
- If input is JSON: writes JSON with added fields (entities, processed_text)
- If input is TXT: writes processed text file
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Dict, Any, Set, Tuple
import re
import unicodedata


def setup_spacy(model_name: str = "en_core_web_sm"):
    try:
        import spacy
        try:
            nlp = spacy.load(model_name)
        except Exception:
            # fallback: try to download via spacy if available
            try:
                from spacy.cli import download as spacy_download
                spacy_download(model_name)
                nlp = spacy.load(model_name)
            except Exception as e:
                raise RuntimeError(
                    f"spaCy model '{model_name}' not installed. Install it with 'poetry run python -m spacy download {model_name}'"
                ) from e
        return nlp
    except ImportError as e:
        raise RuntimeError("spaCy is required. Install dependencies with Poetry first.") from e


ALLOWED_ENTITY_LABELS_DEFAULT = ["PERSON", "GPE", "LOC", "ORG", "PRODUCT", "FAC"]


def normalize_ocr_text(text: str) -> str:
    if not text:
        return ""
    # Unicode normalization
    text = unicodedata.normalize("NFKC", text)
    # Normalize newlines
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # De-hyphenate words broken across line breaks: e.g., "in-
    # formation" -> "information"
    text = re.sub(r"(\S)-\s*\n\s*(\S)", r"\1\2", text)
    # Preserve paragraph breaks while collapsing intra-line breaks and whitespace
    sentinel = "\uFFFFPARA\uFFFF"
    text = re.sub(r"\n\n+", sentinel, text)  # mark paragraphs
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    text = text.replace(sentinel, "\n\n").strip()
    return text


def process_text(
    text: str,
    nlp,
    allowed_entity_labels: Set[str],
    remove_stopwords: bool = True,
    preserve_entity_casing: bool = False,
    do_normalize: bool = True,
) -> Tuple[str, List[Dict[str, Any]]]:
    text_in = normalize_ocr_text(text) if do_normalize else text
    doc = nlp(text_in)

    # Build set of token indices that belong to allowed entity spans
    entity_token_idxs: Set[int] = set()
    entities: List[Dict[str, Any]] = []
    for ent in doc.ents:
        if ent.label_ in allowed_entity_labels:
            entities.append({
                "text": ent.text,
                "label": ent.label_,
                "start": ent.start_char,
                "end": ent.end_char,
            })
            for i in range(ent.start, ent.end):
                entity_token_idxs.add(i)

    out_tokens: List[str] = []
    for i, tok in enumerate(doc):
        if tok.is_space or tok.is_punct:
            continue
        if remove_stopwords and tok.is_stop and i not in entity_token_idxs:
            continue

        if i in entity_token_idxs:
            norm = tok.text if preserve_entity_casing else tok.text.lower()
        else:
            # Lemmatize non-entity tokens
            lemma = tok.lemma_ if tok.lemma_ != "-PRON-" else tok.text
            norm = lemma.lower()
        out_tokens.append(norm)

    processed_text = " ".join(out_tokens).strip()
    return processed_text, entities


def is_json_input(path: str) -> bool:
    try:
        with open(path, "r", encoding="utf-8") as f:
            first = f.read(1)
            return first in ("[", "{")
    except Exception:
        return False


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Post-process extracted text: lowercase, stopwords, NER, lemmatize non-entities")
    p.add_argument("input", help="Path to extracted output (JSON or TXT)")
    p.add_argument("--out", default=None, help="Output path (defaults alongside input)")
    p.add_argument("--model", default="en_core_web_sm", help="spaCy model name")
    p.add_argument("--entities", default=",".join(ALLOWED_ENTITY_LABELS_DEFAULT), help="Comma-separated entity labels to preserve (e.g., PERSON,GPE,LOC)")
    p.add_argument("--keep-stopwords", action="store_true", help="Do not remove stopwords")
    p.add_argument("--per-file-dir", default=None, help="If JSON array input, write per-file processed JSONs into this directory")
    p.add_argument("--preserve-entity-casing", action="store_true", help="Keep original casing for entity tokens in processed text")
    p.add_argument("--no-concat-image-text", action="store_true", help="Do not append image processed text to document processed_text")
    p.add_argument("--no-normalize", action="store_true", help="Disable OCR text normalization (de-hyphenation, whitespace)")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    nlp = setup_spacy(args.model)
    labels = set([s.strip().upper() for s in args.entities.split(",") if s.strip()])
    remove_stop = not args.keep_stopwords
    preserve_entity_casing = args.preserve_entity_casing
    concat_image_text = not args.no_concat_image_text
    do_normalize = not args.no_normalize

    in_path = args.input
    if args.out:
        out_path = args.out
    else:
        base, ext = os.path.splitext(in_path)
        out_path = base + (".processed.json" if ext.lower() == ".json" else ".processed.txt")

    if is_json_input(in_path):
        with open(in_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        is_array = isinstance(data, list)
        items = data if is_array else [data]

        processed_items = []
        for item in items:
            text = item.get("text", "")
            processed_text, entities = process_text(text, nlp, labels, remove_stopwords=remove_stop, preserve_entity_casing=preserve_entity_casing, do_normalize=do_normalize)
            new_item = dict(item)
            new_item["entities"] = entities
            new_item["processed_text"] = processed_text
            # If images are present in the item, process their OCR text too
            if isinstance(new_item.get("images"), list):
                proc_images = []
                for img in new_item["images"]:
                    ocr_text = (img or {}).get("ocr_text", "") or ""
                    if ocr_text.strip():
                        itxt, ients = process_text(ocr_text, nlp, labels, remove_stopwords=remove_stop, preserve_entity_casing=preserve_entity_casing, do_normalize=do_normalize)
                    else:
                        itxt, ients = "", []
                    new_img = dict(img)
                    new_img["processed_text"] = itxt
                    new_img["entities"] = ients
                    proc_images.append(new_img)
                new_item["images"] = proc_images
            # Optionally append image processed_text into the document processed_text
            if concat_image_text and isinstance(new_item.get("images"), list):
                img_texts = [img.get("processed_text", "") for img in new_item["images"] if img.get("processed_text")]
                if img_texts:
                    new_item["processed_text"] = (new_item["processed_text"] + " " + " ".join(img_texts)).strip()

            processed_items.append(new_item)

        # Optional per-file outputs when input is an array
        if is_array and args.per_file_dir:
            out_dir = os.path.abspath(args.per_file_dir)
            os.makedirs(out_dir, exist_ok=True)
            for itm in processed_items:
                base = os.path.basename(itm.get("file", "item")) or "item"
                per_path = os.path.join(out_dir, f"{base}.processed.json")
                with open(per_path, "w", encoding="utf-8") as pf:
                    json.dump(itm, pf, ensure_ascii=False, indent=2)
            print(f"Wrote per-file JSONs to: {out_dir}")

        payload = processed_items if is_array else processed_items[0]
        os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"Wrote JSON: {out_path}")
    else:
        with open(in_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        processed_text, entities = process_text(text, nlp, labels, remove_stopwords=remove_stop)
        os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(processed_text)
        # Also emit sidecar with entities
        ents_path = os.path.splitext(out_path)[0] + ".entities.json"
        with open(ents_path, "w", encoding="utf-8") as f:
            json.dump(entities, f, ensure_ascii=False, indent=2)
        print(f"Wrote text: {out_path}")
        print(f"Wrote entities: {ents_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
