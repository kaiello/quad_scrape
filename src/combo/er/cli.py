from __future__ import annotations

import argparse
import json
import os
import hashlib
from typing import Dict, List, Any, Optional

from .api import simple_ner, simple_link


def _resolve(p: str) -> str:
    return os.path.abspath(os.path.realpath(p))


def _load_normalized_map(norm_dir: str) -> Dict[str, Dict[str, Any]]:
    """Map chunk_id -> {doc_id, text, source_sha1, base} from normalized JSONs."""
    out: Dict[str, Dict[str, Any]] = {}
    for name in os.listdir(norm_dir):
        if not name.endswith('.json'):
            continue
        path = os.path.join(norm_dir, name)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            doc_id = data.get('doc', {}).get('doc_id')
            for ch in data.get('chunks', []):
                text = ch.get('text', '')
                sha1 = hashlib.sha1((text or '').encode('utf-8')).hexdigest()
                out[ch.get('chunk_id')] = {
                    'doc_id': doc_id,
                    'text': text,
                    'source_sha1': sha1,
                    'base': os.path.splitext(name)[0],
                }
        except Exception:
            continue
    return out


def process_embedded(emb_dir: str, norm_dir: str, out_dir: str) -> Dict[str, int]:
    emb_dir = _resolve(emb_dir)
    norm_dir = _resolve(norm_dir)
    out_dir = _resolve(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    mapping = _load_normalized_map(norm_dir)
    counts = {'entities': 0, 'relations': 0, 'files': 0}
    for name in os.listdir(emb_dir):
        if not name.endswith('.embedded.jsonl'):
            continue
        in_path = os.path.join(emb_dir, name)
        base = os.path.splitext(name)[0]
        ents_path = os.path.join(out_dir, f"{base}.entities.jsonl")
        rels_path = os.path.join(out_dir, f"{base}.rels.jsonl")
        ents_out: List[Dict[str, Any]] = []
        rels_out: List[Dict[str, Any]] = []
        with open(in_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
                chunk_id = row.get('chunk_id')
                meta = mapping.get(chunk_id)
                if not meta:
                    continue
                doc_id = meta['doc_id']
                text = meta['text']
                src_sha1 = meta['source_sha1']
                es = simple_ner(text, doc_id, chunk_id, src_sha1)
                rs = simple_link(es, doc_id, chunk_id, src_sha1)
                for e in es:
                    ents_out.append({
                        'id': e.id, 'chunk_id': e.chunk_id, 'doc_id': e.doc_id, 'type': e.type, 'text': e.text,
                        'start': e.start, 'end': e.end, 'conf': e.conf, 'source_sha1': e.source_sha1
                    })
                for r in rs:
                    rels_out.append({
                        'id': r.id, 'head_ent_id': r.head_ent_id, 'tail_ent_id': r.tail_ent_id, 'type': r.type,
                        'conf': r.conf, 'chunk_id': r.chunk_id, 'doc_id': r.doc_id, 'source_sha1': r.source_sha1
                    })
        if ents_out:
            with open(ents_path, 'w', encoding='utf-8', newline='') as ef:
                for obj in ents_out:
                    ef.write(json.dumps(obj, ensure_ascii=False, sort_keys=True))
                    ef.write('\n')
        if rels_out:
            with open(rels_path, 'w', encoding='utf-8', newline='') as rf:
                for obj in rels_out:
                    rf.write(json.dumps(obj, ensure_ascii=False, sort_keys=True))
                    rf.write('\n')
        counts['entities'] += len(ents_out)
        counts['relations'] += len(rels_out)
        counts['files'] += 1
    # Manifest
    manifest = {**counts}
    with open(os.path.join(out_dir, 'manifest.json'), 'w', encoding='utf-8') as mf:
        json.dump(manifest, mf, ensure_ascii=False, sort_keys=True, indent=2)
    return counts


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog='combo er', description='Entity/Relation extraction (simple)')
    ap.add_argument('embedded_dir', help='Directory of *.embedded.jsonl')
    ap.add_argument('--normalized-dir', required=True, help='Directory of normalized JSON to supply chunk text')
    ap.add_argument('--out', required=True, help='Output directory for ER JSONLs')
    args = ap.parse_args(argv)
    try:
        counts = process_embedded(args.embedded_dir, args.normalized_dir, args.out)
        print(f"Wrote ER: files={counts['files']} entities={counts['entities']} rels={counts['relations']}")
        return 0
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1

