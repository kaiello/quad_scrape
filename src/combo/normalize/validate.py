from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List, Optional


NormalizedSchema: Dict[str, Any] = {
    "type": "object",
    "required": ["meta", "doc", "sentences", "chunks", "images"],
    "properties": {
        "meta": {
            "type": "object",
            "required": ["normalizer", "doc_sha1", "n_sentences", "n_chunks"],
            "properties": {
                "normalizer": {
                    "type": "object",
                    "required": ["name", "version", "spec"],
                },
                "doc_sha1": {"type": "string"},
                "n_sentences": {"type": "integer", "minimum": 0},
                "n_chunks": {"type": "integer", "minimum": 0},
            },
            "additionalProperties": True,
        },
        "doc": {
            "type": "object",
            "required": ["doc_id", "source_path", "num_pages", "pages"],
            "properties": {
                "doc_id": {"type": "string"},
                "source_path": {"type": "string"},
                "num_pages": {"type": "integer", "minimum": 1},
                "pages": {"type": "array"},
            },
            "additionalProperties": True,
        },
        "sentences": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["doc_id", "sent_id", "text", "char_start", "char_end"],
                "properties": {
                    "doc_id": {"type": "string"},
                    "sent_id": {"type": "string"},
                    "page": {"type": ["integer", "null"]},
                    "text": {"type": "string"},
                    "char_start": {"type": "integer", "minimum": 0},
                    "char_end": {"type": "integer", "minimum": 0},
                },
                "additionalProperties": True,
            },
        },
        "chunks": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["doc_id", "chunk_id", "text", "sentence_ids", "page_start", "page_end"],
                "properties": {
                    "doc_id": {"type": "string"},
                    "chunk_id": {"type": "string"},
                    "text": {"type": "string"},
                    "sentence_ids": {"type": "array", "items": {"type": "string"}},
                    "page_start": {"type": ["integer", "null"]},
                    "page_end": {"type": ["integer", "null"]},
                },
                "additionalProperties": True,
            },
        },
        "images": {"type": "array"},
    },
    "additionalProperties": False,
}


def _validate_schema(obj: Dict[str, Any]) -> List[str]:
    errs: List[str] = []
    # Minimal inline checks (no external jsonschema dependency)
    for k in ["meta", "doc", "sentences", "chunks", "images"]:
        if k not in obj:
            errs.append(f"missing key: {k}")
    doc = obj.get("doc", {})
    for k in ["doc_id", "source_path", "num_pages", "pages"]:
        if k not in doc:
            errs.append(f"doc missing: {k}")
    if not isinstance(doc.get("pages", []), list):
        errs.append("doc.pages must be an array")
    if not isinstance(obj.get("sentences", []), list):
        errs.append("sentences must be an array")
    if not isinstance(obj.get("chunks", []), list):
        errs.append("chunks must be an array")
    if not isinstance(obj.get("images", []), list):
        errs.append("images must be an array")
    return errs


def _tokens(s: str) -> int:
    return len((s or "").split())


def validate_normalized_object(obj: Dict[str, Any], token_budget: int = 512) -> List[str]:
    errs = _validate_schema(obj)
    if errs:
        return errs

    # Token budget and consecutive sentence checks per chunk
    # Build index mapping of sentence_id -> order and page
    idx: Dict[str, int] = {}
    pages: Dict[str, Optional[int]] = {}
    for i, s in enumerate(obj.get("sentences", [])):
        sid = s.get("sent_id")
        if isinstance(sid, str):
            idx[sid] = i
            pages[sid] = s.get("page")

    for ch in obj.get("chunks", []):
        text = ch.get("text", "")
        if _tokens(text) > token_budget:
            errs.append(f"chunk {ch.get('chunk_id')} exceeds token budget")
        sids = ch.get("sentence_ids", []) or []
        if not sids:
            continue
        # Consecutive indices
        ords = [idx.get(s) for s in sids]
        if any(o is None for o in ords):
            errs.append(f"chunk {ch.get('chunk_id')} references unknown sentence_ids")
        else:
            for a, b in zip(ords, ords[1:]):
                if (b - a) != 1:
                    errs.append(f"chunk {ch.get('chunk_id')} has non-consecutive sentences")
        # Page range
        pvals = [pages.get(s) for s in sids if s in pages]
        if pvals:
            pmin = min(p for p in pvals if p is not None)
            pmax = max(p for p in pvals if p is not None)
            if ch.get("page_start") not in (None, pmin) or ch.get("page_end") not in (None, pmax):
                errs.append(f"chunk {ch.get('chunk_id')} page range mismatch")
    # Slice-equality invariant using embedded doc.pages
    pages_arr = obj.get("doc", {}).get("pages", []) or []
    for s in obj.get("sentences", []):
        try:
            page = s.get("page") or 1
            src = pages_arr[page - 1]
            a = int(s.get("char_start", 0))
            b = int(s.get("char_end", 0))
            if s.get("text", "") != src[a:b]:
                errs.append(f"slice mismatch for sent_id={s.get('sent_id')}")
        except Exception:
            errs.append(f"slice check failed for sent_id={s.get('sent_id')}")
    return errs


def validate_dir(normalized_dir: str, token_budget: int = 512) -> Dict[str, List[str]]:
    results: Dict[str, List[str]] = {}
    for name in os.listdir(normalized_dir):
        if not name.lower().endswith(".json"):
            continue
        path = os.path.join(normalized_dir, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                obj = json.load(f)
            errs = validate_normalized_object(obj, token_budget=token_budget)
            results[name] = errs
        except Exception as e:
            results[name] = [f"failed to read/parse: {e}"]
    return results


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="combo validate", description="Validate normalized JSON files (dir or file)")
    ap.add_argument("target", help="Directory of normalized .json files or a single file")
    ap.add_argument("--token-budget", type=int, default=512)
    args = ap.parse_args(argv)
    try:
        if os.path.isdir(args.target):
            results = validate_dir(args.target, token_budget=args.token_budget)
        else:
            # single file
            try:
                with open(args.target, "r", encoding="utf-8") as f:
                    obj = json.load(f)
                errs = validate_normalized_object(obj, token_budget=args.token_budget)
                results = {os.path.basename(args.target): errs}
            except Exception as e:
                results = {os.path.basename(args.target): [f"failed to read/parse: {e}"]}
        total = len(results)
        failures = sum(1 for v in results.values() if v)
        for fname, errs in results.items():
            status = "OK" if not errs else "FAIL"
            print(f"{fname}: {status}")
            if errs:
                for e in errs:
                    print(f"  - {e}")
        print(f"Validated {total} file(s); failures: {failures}")
        # Exit codes: 0 success, 2 validation/schema failures
        return 0 if failures == 0 else 2
    except Exception as e:
        # Unexpected exceptions: exit code 1
        print(f"Unexpected error: {e}")
        return 1
