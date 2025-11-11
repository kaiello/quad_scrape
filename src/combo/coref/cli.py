from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from typing import Dict, List, Any, Optional

from .within_doc import resolve_coref, _derive_mention_features


def _resolve(p: str) -> str:
    return os.path.abspath(os.path.realpath(p))


def _read_entities(path: str) -> List[Dict[str, Any]]:
    ents: List[Dict[str, Any]] = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            ents.append(json.loads(line))
    return ents


def _write_jsonl(path: str, rows: List[Dict[str, Any]]) -> int:
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True))
            f.write('\n')
    return len(rows)


def _build_chains(ents: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    # Simple chain building via antecedent links
    parent: Dict[str, str] = {}

    def find(x: str) -> str:
        while parent.get(x, x) != x:
            x = parent[x] = parent.get(parent[x], parent[x])
        return parent.get(x, x)

    def unite(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    mention_ids: List[str] = []
    for e in ents:
        mid = e.get('mention_id') or f"{e.get('doc_id')}:{e.get('chunk_id')}:{e.get('start')}-{e.get('end')}"
        mention_ids.append(mid)
        parent.setdefault(mid, mid)
        ant = e.get('antecedent_mention_id')
        if ant:
            parent.setdefault(ant, ant)
            unite(mid, ant)

    groups: Dict[str, List[str]] = defaultdict(list)
    for mid in mention_ids:
        groups[find(mid)].append(mid)
    return groups


def process_er_dir(er_dir: str, out_dir: str, max_sent_back: int, max_mentions_back: int) -> Dict[str, Any]:
    er_dir = _resolve(er_dir)
    out_dir = _resolve(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    all_stats = Counter()
    rules_hist = Counter()
    docs = 0
    for name in os.listdir(er_dir):
        if not name.endswith('.entities.jsonl'):
            continue
        in_path = os.path.join(er_dir, name)
        ents = _read_entities(in_path)
        # Derive minimal features if absent
        ents = [_derive_mention_features(e) for e in ents]
        resolved = resolve_coref(ents, max_sent_back=max_sent_back, max_mentions_back=max_mentions_back)
        # Write augmented entities
        out_entities = os.path.join(out_dir, name)
        _write_jsonl(out_entities, resolved)
        # Chains per document (approximate per file)
        chains = _build_chains(resolved)
        chain_rows: List[Dict[str, Any]] = []
        doc_id = (resolved[0].get('doc_id') if resolved else None) or 'doc'
        chain_rows.append({
            'doc_id': doc_id,
            'chains': [{'chain_id': f"{doc_id}:{i}", 'mention_ids': mids} for i, mids in enumerate(chains.values())],
            'stats': {'mentions': len(resolved), 'chains': len(chains), 'resolved': sum(1 for e in resolved if e.get('antecedent_mention_id')), 'pronouns': sum(1 for e in resolved if e.get('is_pronoun'))},
        })
        out_chains = os.path.join(out_dir, os.path.splitext(name)[0] + '.coref_chains.jsonl')
        _write_jsonl(out_chains, chain_rows)
        # Stats
        docs += 1
        all_stats['mentions'] += len(resolved)
        all_stats['pronouns_total'] += sum(1 for e in resolved if e.get('is_pronoun'))
        all_stats['resolved'] += sum(1 for e in resolved if e.get('antecedent_mention_id'))
        all_stats['unresolved'] += sum(1 for e in resolved if e.get('is_pronoun') and not e.get('antecedent_mention_id'))
        for e in resolved:
            rules_hist[e.get('coref_rule', 'unresolved')] += 1

    # Run report
    rep_dir = os.path.join(out_dir, '_reports')
    os.makedirs(rep_dir, exist_ok=True)
    with open(os.path.join(rep_dir, 'run_report.json'), 'w', encoding='utf-8') as f:
        json.dump({
            'docs': docs,
            **all_stats,
            'rules_fired': dict(rules_hist),
        }, f, ensure_ascii=False, sort_keys=True, indent=2)
    return {'docs': docs, **all_stats}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog='combo coref', description='Within-document coreference (heuristic)')
    ap.add_argument('er_dir', help='Directory with *.entities.jsonl')
    ap.add_argument('--out', required=True, help='Output directory for coref results')
    ap.add_argument('--max-sent-back', type=int, default=3)
    ap.add_argument('--max-mentions-back', type=int, default=30)
    args = ap.parse_args(argv)
    try:
        process_er_dir(args.er_dir, args.out, args.max_sent_back, args.max_mentions_back)
        return 0
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1

