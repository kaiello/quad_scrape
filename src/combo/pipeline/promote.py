from __future__ import annotations

import argparse
import json
import os
import time
from collections import defaultdict, Counter
from statistics import mean
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from ._promote_utils import (
    domain_range_ok,
    entity_keys_present,
    missing_merge_keys,
    labels_satisfy,
    predicate_specific_ok,
    stable_json_sort_key,
    type_constraints_ok,
)


def _resolve(p: str) -> str:
    return os.path.abspath(os.path.realpath(p))


def _read_jsonl(path: str) -> Iterable[Dict[str, Any]]:
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            yield json.loads(line)


def _write_jsonl(path: str, rows: List[Dict[str, Any]]) -> int:
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    # Deterministic line ordering
    rows_sorted = sorted(rows, key=stable_json_sort_key)
    with open(path, 'w', encoding='utf-8', newline='') as f:
        for r in rows_sorted:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True))
            f.write('\n')
    return len(rows_sorted)


def _load_schema(schema_path: str) -> Dict[str, Any]:
    with open(schema_path, 'r', encoding='utf-8') as f:
        text = f.read()
    # Try YAML first if available
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text)
    except Exception:
        # Fallback to JSON
        return json.loads(text)


def _schema_lookup(schema: Mapping[str, Any]) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
    version = str(schema.get('schema_version') or '1.0.0')
    entities = schema.get('entities') or {}
    relations = schema.get('relations') or {}
    return version, entities, relations


def _bucket_relations(mentions_iter: Iterable[Dict[str, Any]]) -> Tuple[Dict[Tuple[str, str, str], List[Dict[str, Any]]], Counter]:
    buckets: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    counts = Counter()
    for m in mentions_iter:
        sid = m.get('subj_canonical_id')
        oid = m.get('obj_canonical_id')
        pred = m.get('predicate')
        if not sid or not oid or not pred:
            continue
        k = (sid, pred, oid)
        buckets[k].append(m)
        counts['mentions_relations'] += 1
    return buckets, counts


def _aggregate_relation_group(group: List[Dict[str, Any]], max_mentions: int = 20) -> Dict[str, Any]:
    confs = [float(x.get('confidence') or 0.0) for x in group]
    avg_conf = mean(confs) if confs else 0.0
    sent_ids = sorted({str(x.get('sent_id')) for x in group if x.get('sent_id')})
    doc_ids = sorted({str(x.get('doc_id')) for x in group if x.get('doc_id')})
    mentions = []
    for m in sorted(group, key=lambda r: (str(r.get('doc_id')), str(r.get('sent_id')), stable_json_sort_key(r))):
        mentions.append({
            'doc_id': m.get('doc_id'),
            'sent_id': m.get('sent_id'),
            'span': m.get('span'),
            'confidence': float(m.get('confidence') or 0.0),
        })
        if len(mentions) >= max_mentions:
            break
    return {
        'avg_confidence': avg_conf,
        'ev_count': len(sent_ids),
        'doc_count': len(doc_ids),
        'mentions': mentions,
    }


def _collect_entity_evidence(mentions_iter: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    by_canon: Dict[str, Dict[str, Any]] = {}
    for m in mentions_iter:
        cid = m.get('canonical_id')
        if not cid:
            continue
        rec = by_canon.setdefault(cid, {'sent_ids': set(), 'doc_ids': set(), 'count': 0})
        if m.get('sent_id'):
            rec['sent_ids'].add(str(m['sent_id']))
        if m.get('doc_id'):
            rec['doc_ids'].add(str(m['doc_id']))
        rec['count'] += 1
    # Collapse to counts
    out: Dict[str, Dict[str, Any]] = {}
    for cid, r in by_canon.items():
        out[cid] = {
            'ev_count': len(r['sent_ids']),
            'doc_count': len(r['doc_ids']),
            'mention_count': r['count'],
        }
    return out


def promote(
    mentions_entities_path: str,
    mentions_relations_path: str,
    linked_entities_path: str,
    out_dir: Optional[str] = None,
    schema_path: Optional[str] = None,
    *,
    conf_thr: Optional[float] = None,
    min_ev: Optional[int] = None,
    min_evidence: Optional[int] = None,
) -> Tuple[str, str, str]:
    t0 = time.time()
    if out_dir is None or schema_path is None:
        raise ValueError("promote requires out_dir and schema_path (positional or keyword)")
    out_dir = _resolve(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(os.path.join(out_dir, 'quarantine'), exist_ok=True)
    os.makedirs(os.path.join(out_dir, '_reports'), exist_ok=True)

    schema = _load_schema(_resolve(schema_path))
    schema_version, schema_entities, schema_rels = _schema_lookup(schema)
    # Resolve thresholds from schema defaults when not provided
    defaults = schema.get('promotion') or schema.get('promotion_defaults') or {}
    if conf_thr is None:
        conf_thr = float(defaults.get('conf_thr', 0.7))
    # Prefer min_ev if provided, else min_evidence, else schema default
    if min_ev is not None:
        min_evidence_val = int(min_ev)
    elif min_evidence is not None:
        min_evidence_val = int(min_evidence)
    else:
        min_evidence_val = int(defaults.get('min_evidence', 2))

    # Load linked canonical entities
    canon_idx: Dict[str, Dict[str, Any]] = {}
    for row in _read_jsonl(_resolve(linked_entities_path)):
        cid = row.get('canonical_id')
        if cid:
            canon_idx[cid] = row

    # Load entity evidence and reset iterator for relations aggregation
    ents_path = _resolve(mentions_entities_path)
    rels_path = _resolve(mentions_relations_path)

    with open(ents_path, 'r', encoding='utf-8') as f:
        ent_mentions = [json.loads(line) for line in f if line.strip()]
    ent_ev = _collect_entity_evidence(ent_mentions)

    with open(rels_path, 'r', encoding='utf-8') as f:
        rel_mentions = [json.loads(line) for line in f if line.strip()]
    buckets, counts = _bucket_relations(rel_mentions)
    counts['relation_groups'] = len(buckets)
    counts['mentions_entities'] = len(ent_mentions)

    promoted_rel_rows: List[Dict[str, Any]] = []
    quarantined_rel_rows: List[Dict[str, Any]] = []
    promoted_entity_ids: set[str] = set()

    # Process relations per bucket deterministically
    for (sid, pred, oid) in sorted(buckets.keys(), key=lambda k: (k[0], k[1], k[2])):
        group = buckets[(sid, pred, oid)]
        agg = _aggregate_relation_group(group)
        reasons: List[str] = []
        # Thresholds
        if not (agg['avg_confidence'] >= float(conf_thr) and agg['ev_count'] >= int(min_evidence_val)):
            reasons.append('below_threshold')
        # Predicate allowlist
        rule = schema_rels.get(pred)
        if not rule:
            reasons.append('predicate_not_allowed')
        # Subject and object presence
        subj = canon_idx.get(sid)
        obj = canon_idx.get(oid)
        if not subj:
            reasons.append('missing_subject')
        if not obj:
            reasons.append('missing_object')
        # Keys/constraints on entities
        subj_missing: List[str] = []
        obj_missing: List[str] = []
        if subj:
            subj_missing = missing_merge_keys(subj, schema_entities)
            if subj_missing:
                reasons.append(f"missing_keys:subject:{','.join(subj_missing)}")
            if not entity_keys_present(subj, schema_entities):
                # Keep constraint parity (required fields beyond merge keys)
                pass
        if obj:
            obj_missing = missing_merge_keys(obj, schema_entities)
            if obj_missing:
                reasons.append(f"missing_keys:object:{','.join(obj_missing)}")
            if not entity_keys_present(obj, schema_entities):
                pass
        if subj and not type_constraints_ok(subj, schema_entities):
            reasons.append('type_constraint_failed')
        if obj and not type_constraints_ok(obj, schema_entities):
            reasons.append('type_constraint_failed')
        # Domain/range and predicate-specific constraints
        if rule and subj and obj:
            if not domain_range_ok(subj.get('labels') or [], obj.get('labels') or [], rule):
                reasons.append('domain_range_mismatch')
            # Gather rel props from one mention (if any)
            rel_props = None
            for m in group:
                if m.get('props'):
                    rel_props = m.get('props')
                    break
            if not predicate_specific_ok(pred, subj, obj, rel_props, schema_entities):
                reasons.append('predicate_constraint_failed')

        if reasons:
            # Include compact examples for triage
            ex = []
            for m in sorted(group, key=lambda r: (str(r.get('doc_id')), str(r.get('sent_id')), stable_json_sort_key(r)))[:3]:
                ex.append({'doc_id': m.get('doc_id'), 'sent_id': m.get('sent_id')})
            quarantined_rel_rows.append({
                'subj': {'canonical_id': sid},
                'predicate': pred,
                'obj': {'canonical_id': oid},
                'group_key': [sid, pred, oid],
                'evidence': agg,
                'policy': {'conf_thr': float(conf_thr), 'min_ev': int(min_evidence_val)},
                'reasons': sorted(set(reasons)),
                'examples': ex,
                'kind': 'relation',
                'provenance': {'schema_version': schema_version},
            })
            continue

        # Success: promote
        # sample props carry-through
        rel_props = None
        for m in group:
            if m.get('props'):
                rel_props = m.get('props')
                break
        promoted_rel_rows.append({
            'subj': {'canonical_id': sid, 'labels': subj.get('labels') if subj else []},
            'predicate': pred,
            'obj': {'canonical_id': oid, 'labels': obj.get('labels') if obj else []},
            'props': rel_props or {},
            'evidence': agg,
            'policy': {'conf_thr': float(conf_thr), 'min_ev': int(min_evidence_val)},
            'provenance': {'schema_version': schema_version},
        })
        promoted_entity_ids.add(sid)
        promoted_entity_ids.add(oid)

    # Entities to emit: in promoted relations OR standalone >= min_evidence
    for cid, stats in sorted(ent_ev.items()):
        if stats.get('ev_count', 0) >= int(min_evidence_val):
            promoted_entity_ids.add(cid)

    promoted_ent_rows: List[Dict[str, Any]] = []
    quarantined_ent_rows: List[Dict[str, Any]] = []
    for cid in sorted(promoted_entity_ids):
        ce = canon_idx.get(cid)
        if not ce:
            quarantined_ent_rows.append({
                'canonical_id': cid,
                'reasons': ['missing_object'],
                'provenance': {'schema_version': schema_version},
            })
            continue
        reasons: List[str] = []
        missing = missing_merge_keys(ce, schema_entities)
        if missing:
            reasons.append(f"missing_keys:{','.join(missing)}")
        if not entity_keys_present(ce, schema_entities):
            reasons.append('missing_entity_keys')
        if not type_constraints_ok(ce, schema_entities):
            reasons.append('type_constraint_failed')
        stats = ent_ev.get(cid) or {'ev_count': 0, 'doc_count': 0}
        if reasons:
            quarantined_ent_rows.append({
                'kind': 'entity',
                'canonical_id': cid,
                'type': ce.get('type'),
                'labels': ce.get('labels'),
                'reasons': sorted(set(reasons)),
                'provenance': {'schema_version': schema_version, 'ev_count': stats.get('ev_count', 0), 'doc_count': stats.get('doc_count', 0)},
            })
            continue
        promoted_ent_rows.append({
            'canonical_id': cid,
            'type': ce.get('type'),
            'labels': ce.get('labels'),
            'key': ce.get('key') or {},
            'props': ce.get('props') or {},
            'provenance': {'schema_version': schema_version, 'ev_count': stats.get('ev_count', 0), 'doc_count': stats.get('doc_count', 0)},
        })

    # Writes
    facts_entities_path = os.path.join(out_dir, 'facts.entities.jsonl')
    facts_relations_path = os.path.join(out_dir, 'facts.relations.jsonl')
    q_entities_path = os.path.join(out_dir, 'quarantine', 'entities.jsonl')
    q_relations_path = os.path.join(out_dir, 'quarantine', 'relations.jsonl')
    _write_jsonl(facts_entities_path, promoted_ent_rows)
    _write_jsonl(facts_relations_path, promoted_rel_rows)
    _write_jsonl(q_entities_path, quarantined_ent_rows)
    _write_jsonl(q_relations_path, quarantined_rel_rows)

    # Report
    report = {
        'schema_version': schema_version,
        'conf_thr': float(conf_thr),
        'min_ev': int(min_evidence_val),
        'counts': {
            'mentions_entities': counts.get('mentions_entities', 0),
            'mentions_relations': counts.get('mentions_relations', 0),
            'relation_groups': counts.get('relation_groups', 0),
            'promoted_relations': len(promoted_rel_rows),
            'promoted_entities': len(promoted_ent_rows),
            'quarantined_relations': len(quarantined_rel_rows),
            'quarantined_entities': len(quarantined_ent_rows),
        },
        'duration_seconds': round(time.time() - t0, 6),
        'errors': 0,
    }
    with open(os.path.join(out_dir, '_reports', 'run_report.json'), 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, sort_keys=True, indent=2)
    # Return paths for convenience/compat with toy test bundle
    return facts_entities_path, facts_relations_path, os.path.join(out_dir, 'quarantine')


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog='combo promote', description='Promote trusted facts from mentions and linked canonicals')
    ap.add_argument('mentions_entities_path')
    ap.add_argument('mentions_relations_path')
    ap.add_argument('linked_entities_path')
    ap.add_argument('--schema', required=True, dest='schema_path')
    ap.add_argument('--conf', type=float, default=None, dest='conf_thr')
    ap.add_argument('--min-evidence', type=int, default=None, dest='min_evidence')
    ap.add_argument('--out', required=True, dest='out_dir')
    ap.add_argument('--doctor', action='store_true', help='Run preflight checks only')
    ap.add_argument('--md-out', default=None, help='Optional Markdown output for doctor preflight')
    args = ap.parse_args(argv)

    try:
        schema = _load_schema(_resolve(args.schema_path))
        defaults = schema.get('promotion') or schema.get('promotion_defaults') or {}
        conf_thr = args.conf_thr if args.conf_thr is not None else float(defaults.get('conf_thr', 0.7))
        min_ev = args.min_evidence if args.min_evidence is not None else int(defaults.get('min_evidence', 2))
        if args.doctor:
            from .doctor import run_doctor
            report_dir = os.path.join(_resolve(args.out_dir), '_reports')
            _, code = run_doctor(
                args.mentions_entities_path,
                args.mentions_relations_path,
                args.linked_entities_path,
                args.schema_path,
                float(conf_thr),
                int(min_ev),
                report_dir,
                args.md_out,
            )
            return int(code)
        else:
            promote(
                args.mentions_entities_path,
                args.mentions_relations_path,
                args.linked_entities_path,
                args.out_dir,
                args.schema_path,
                conf_thr=conf_thr,
                min_ev=min_ev,
            )
            return 0
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1
