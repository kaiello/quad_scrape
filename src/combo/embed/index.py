from __future__ import annotations

import argparse
import json
import os
from typing import List, Dict, Any, Optional

import numpy as np


def _resolve(path: str) -> str:
    return os.path.abspath(os.path.realpath(path))


def load_embeddings(dir_path: str) -> tuple[np.ndarray, List[Dict[str, Any]]]:
    vecs: List[List[float]] = []
    meta: List[Dict[str, Any]] = []
    for name in os.listdir(dir_path):
        if not name.endswith('.embedded.jsonl'):
            continue
        with open(os.path.join(dir_path, name), 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                obj = json.loads(line)
                vecs.append(obj['embedding'])
                meta.append({k: obj.get(k) for k in ('doc_id', 'chunk_id', 'model', 'dim')})
    arr = np.asarray(vecs, dtype=np.float32) if vecs else np.zeros((0, 0), dtype=np.float32)
    return arr, meta


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog='combo index', description='Build NPZ index from embedded JSONL files')
    ap.add_argument('emb_dir', help='Directory containing *.embedded.jsonl')
    ap.add_argument('--out', required=True, help='Output directory for NPZ index')
    args = ap.parse_args(argv)
    try:
        emb_dir = _resolve(args.emb_dir)
        out_dir = _resolve(args.out)
        os.makedirs(out_dir, exist_ok=True)
        arr, meta = load_embeddings(emb_dir)
        npz_path = os.path.join(out_dir, 'embeddings.npz')
        np.savez(npz_path, X=arr)
        print(f"[ok] wrote {npz_path} with shape={arr.shape}")
        return 0
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1

