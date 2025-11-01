from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter, defaultdict
from typing import Dict, List, Any, Optional, Tuple

from .registry import open_registry, get_or_create_canonical, add_alias, add_external_id, normalize_label
from .external_sources import wikidata_cache as wd
from .external_sources import uei_cache as uei


def _resolve(p: str) -> str:
    """Resolves a path to an absolute path.

    Args:
        p: The path to resolve.

    Returns:
        The absolute path.
    """
    return os.path.abspath(os.path.realpath(p))


def _iter_entities_from_dir(base_dir: str) -> Dict[str, List[Dict[str, Any]]]:
    """Iterates over entities from a directory of JSONL files.

    Args:
        base_dir: The directory to iterate over.

    Returns:
        A dictionary mapping document base names to a list of entities.
    """
    docs: Dict[str, List[Dict[str, Any]]] = {}
    for name in os.listdir(base_dir):
        if not name.endswith('.entities.jsonl'):
            continue
        path = os.path.join(base_dir, name)
        base = os.path.splitext(name)[0]
        if base.endswith('.entities'):
            base = base[:-9]
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                ent = json.loads(line)
                ent['_base'] = base
                docs.setdefault(base, []).append(ent)
    return docs


def _write_jsonl(path: str, rows: List[Dict[str, Any]]) -> int:
    """Writes a list of dictionaries to a JSONL file.

    Args:
        path: The path to the output file.
        rows: The list of dictionaries to write.

    Returns:
        The number of rows written.
    """
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True))
            f.write('\n')
    return len(rows)


def link_entities(input_dir: str, out_dir: str, registry_path: str, *, link_conf: float = 0.75, enable_fts: bool = False, materialize_blocking: bool = False, adapters: Optional[List[str]] = None, adapter_paths: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Links entities across documents.

    This function iterates over entities from the input directory, links them
    to a canonical registry, and writes the linked entities to the output
    directory.

    Args:
        input_dir: The directory containing the entity files.
        out_dir: The directory to write the linked entities to.
        registry_path: The path to the SQLite registry file.
        link_conf: The confidence threshold for linking.
        enable_fts: Whether to enable full-text search in the registry.
        materialize_blocking: Whether to materialize blocking keys.
        adapters: A list of external adapters to use.
        adapter_paths: A dictionary mapping adapter names to cache paths.

    Returns:
        A dictionary of statistics.
    """
    input_dir = _resolve(input_dir)
    out_dir = _resolve(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    conn = open_registry(_resolve(registry_path), enable_fts=enable_fts)

    docs = _iter_entities_from_dir(input_dir)

    # Load adapter caches
    adapters = adapters or []
    adapter_paths = adapter_paths or {}
    wd_cache = wd.load_cache(adapter_paths.get('wikidata')) if 'wikidata' in adapters else {}
    uei_cache = uei.load_cache(adapter_paths.get('uei')) if 'uei' in adapters else {}

    totals = Counter()
    for base, ents in docs.items():
        # Group per (type, canonical key)
        groups: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for e in ents:
            lab = (e.get('label') or e.get('type') or '').upper()
            text = e.get('text') or e.get('label') or ''
            key_val = e.get('resolved_entity_id') or e.get('entity_id') or normalize_label(text)
            k = (lab, key_val)
            g = groups.setdefault(k, {"type": lab, "names": Counter(), "mention_ids": [], "doc_id": e.get('doc_id')})
            g['names'][text] += 1
            if e.get('mention_id'):
                g['mention_ids'].append(e['mention_id'])

        rows: List[Dict[str, Any]] = []
        for (lab, key_val), g in groups.items():
            # Choose display name by highest count then lexicographic
            name = sorted(g['names'].items(), key=lambda kv: (-kv[1], kv[0]))[0][0] if g['names'] else ''
            # Create/get canonical in registry
            can_id = get_or_create_canonical(conn, lab, key_val, primary_name=name)
            add_alias(conn, can_id, name)
            # Attach external IDs
            norm_name = normalize_label(name)
            ext_ids: List[Dict[str, str]] = []
            if wd_cache:
                wdid = wd.lookup(norm_name, wd_cache)
                if wdid:
                    add_external_id(conn, can_id, 'wikidata', wdid)
                    ext_ids.append({"source": "wikidata", "id": wdid})
            if uei_cache and lab in {'ORG', 'ORGANIZATION'}:
                u = uei.lookup(norm_name, uei_cache)
                if u:
                    add_external_id(conn, can_id, 'uei', u)
                    ext_ids.append({"source": "uei", "id": u})

            rows.append({
                'doc_id': g.get('doc_id'),
                'canonical_id': can_id,
                'type': lab,
                'name': name,
                'mention_ids': sorted(g['mention_ids']),
                'external_ids': sorted(ext_ids, key=lambda d: (d['source'], d['id'])) if ext_ids else [],
            })
        # Deterministic sort (lexicographic on serialized lines)
        rows.sort(key=lambda r: json.dumps(r, ensure_ascii=False, sort_keys=True))
        out_path = os.path.join(out_dir, 'linked.entities.jsonl')
        _write_jsonl(out_path, rows)
        totals['docs'] += 1
        totals['entities'] += len(rows)

    # Report
    rep_dir = os.path.join(out_dir, '_reports')
    os.makedirs(rep_dir, exist_ok=True)
    with open(os.path.join(rep_dir, 'run_report.json'), 'w', encoding='utf-8') as f:
        json.dump({'docs': totals.get('docs', 0), 'entities': totals.get('entities', 0), 'errors': 0}, f, ensure_ascii=False, sort_keys=True, indent=2)
    conn.close()
    return dict(totals)


def main(argv: Optional[List[str]] = None) -> int:
    """The main entry point for the command-line interface.

    This function parses command-line arguments and calls `link_entities` to
    link entities across documents.

    Args:
        argv: A list of command-line arguments.

    Returns:
        An exit code.
    """
    ap = argparse.ArgumentParser(prog='combo link', description='Cross-doc entity linking with SQLite registry and offline adapters')
    ap.add_argument('input_dir', help='Directory with *.entities.jsonl (coref-augmented preferred)')
    ap.add_argument('--registry', required=True, help='Path to SQLite registry file')
    ap.add_argument('--out', required=True, help='Output directory for linked results')
    ap.add_argument('--link-conf', type=float, default=0.75)
    ap.add_argument('--enable-fts', action='store_true')
    ap.add_argument('--materialize-blocking', action='store_true')
    ap.add_argument('--adapters', default='', help='CSV adapters: wikidata,uei')
    ap.add_argument('--wikidata-cache', default=None)
    ap.add_argument('--uei-cache', default=None)
    args = ap.parse_args(argv)
    try:
        adapters = [s.strip() for s in args.adapters.split(',') if s.strip()]
        adapter_paths = {'wikidata': args.wikidata_cache, 'uei': args.uei_cache}
        link_entities(
            args.input_dir,
            args.out,
            args.registry,
            link_conf=args.link_conf,
            enable_fts=args.enable_fts,
            materialize_blocking=args.materialize_blocking,
            adapters=adapters,
            adapter_paths=adapter_paths,
        )
        return 0
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1
