from __future__ import annotations

import json
import os
from pathlib import Path

from src.combo.pipeline.promote import promote


def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True))
            f.write('\n')


def load_jsonl(path: Path):
    with path.open('r', encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def schema_path_repo() -> str:
    return os.path.abspath(os.path.join('src', 'combo', 'schema', 'semantic_contract.yaml'))


def test_happy_path_trl_and_requirement(tmp_path: Path):
    # Linked canonical entities
    tech_id = 'tech:abc'
    trl_id = 'trl:0008'
    req_id = 'req:1'
    linked = [
        {
            'canonical_id': tech_id,
            'type': 'dbo_Technology',
            'labels': ['kb_Technology', 'Technology'],
            'key': {'uri': 'http://ex/tech/railgun'},
            'props': {'name': 'Railgun'},
        },
        {
            'canonical_id': trl_id,
            'type': 'kb_TRL',
            'labels': ['TRL'],
            'key': {'value': 8},
            'props': {},
        },
        {
            'canonical_id': req_id,
            'type': 'kb_Requirement',
            'labels': ['Requirement'],
            'key': {'id': 'R-1'},
            'props': {'type': 'functional', 'priority': 'high'},
        },
    ]
    # Mentions: entities (two mentions for tech to satisfy standalone too)
    ents = [
        {'mention_id': 'm1', 'type': 'dbo_Technology', 'labels': ['kb_Technology', 'Technology'], 'surface': 'railgun', 'canonical_id': tech_id, 'doc_id': 'd1', 'sent_id': 's1', 'span': [0, 5], 'confidence': 0.9, 'props': {'uri': 'http://ex/tech/railgun', 'name': 'Railgun'}},
        {'mention_id': 'm2', 'type': 'dbo_Technology', 'labels': ['kb_Technology', 'Technology'], 'surface': 'railgun', 'canonical_id': tech_id, 'doc_id': 'd1', 'sent_id': 's2', 'span': [10, 20], 'confidence': 0.88, 'props': {'uri': 'http://ex/tech/railgun'}},
    ]
    # Mentions: relations (two evidences)
    rels = [
        {'mention_id': 'mr1a', 'predicate': 'STARTS_AT_TRL', 'subj_canonical_id': tech_id, 'subj_labels': ['kb_Technology', 'Technology'], 'obj_canonical_id': trl_id, 'obj_labels': ['TRL'], 'doc_id': 'd1', 'sent_id': 's1', 'span': [20, 30], 'confidence': 0.86, 'props': {'value': 8}},
        {'mention_id': 'mr1b', 'predicate': 'STARTS_AT_TRL', 'subj_canonical_id': tech_id, 'subj_labels': ['kb_Technology', 'Technology'], 'obj_canonical_id': trl_id, 'obj_labels': ['TRL'], 'doc_id': 'd2', 'sent_id': 's3', 'span': [0, 1], 'confidence': 0.84, 'props': {'value': 8}},
        {'mention_id': 'mr2a', 'predicate': 'HAS_REQUIREMENT', 'subj_canonical_id': tech_id, 'subj_labels': ['kb_Technology', 'Technology'], 'obj_canonical_id': req_id, 'obj_labels': ['Requirement'], 'doc_id': 'd1', 'sent_id': 's2', 'span': [40, 50], 'confidence': 0.9, 'props': {'type': 'functional'}},
        {'mention_id': 'mr2b', 'predicate': 'HAS_REQUIREMENT', 'subj_canonical_id': tech_id, 'subj_labels': ['kb_Technology', 'Technology'], 'obj_canonical_id': req_id, 'obj_labels': ['Requirement'], 'doc_id': 'd3', 'sent_id': 's4', 'span': [0, 1], 'confidence': 0.91, 'props': {'type': 'functional'}},
    ]

    ment_e = tmp_path / 'mentions.entities.jsonl'
    ment_r = tmp_path / 'mentions.relations.jsonl'
    linked_p = tmp_path / 'linked.entities.jsonl'
    write_jsonl(ment_e, ents)
    write_jsonl(ment_r, rels)
    write_jsonl(linked_p, linked)

    out_dir = tmp_path / 'facts'
    promote(str(ment_e), str(ment_r), str(linked_p), schema_path=schema_path_repo(), conf_thr=0.7, min_evidence=2, out_dir=str(out_dir))

    facts_rels = load_jsonl(out_dir / 'facts.relations.jsonl')
    facts_ents = load_jsonl(out_dir / 'facts.entities.jsonl')
    q_rels = load_jsonl(out_dir / 'quarantine' / 'relations.jsonl')
    q_ents = load_jsonl(out_dir / 'quarantine' / 'entities.jsonl')

    assert len(facts_rels) == 2
    preds = sorted([r['predicate'] for r in facts_rels])
    assert preds == ['HAS_REQUIREMENT', 'STARTS_AT_TRL']
    assert any(e['canonical_id'] == tech_id for e in facts_ents)
    assert any(e['canonical_id'] == trl_id for e in facts_ents)
    assert any(e['canonical_id'] == req_id for e in facts_ents)
    assert not q_rels and not q_ents


def test_threshold_gate_quarantine(tmp_path: Path):
    tech_id = 'tech:abc'
    trl_id = 'trl:0008'
    linked = [
        {'canonical_id': tech_id, 'type': 'dbo_Technology', 'labels': ['Technology'], 'key': {'uri': 'u'}, 'props': {}},
        {'canonical_id': trl_id, 'type': 'kb_TRL', 'labels': ['TRL'], 'key': {'value': 8}, 'props': {}},
    ]
    ents = [
        {'mention_id': 'm1', 'type': 'dbo_Technology', 'labels': ['Technology'], 'surface': 't', 'canonical_id': tech_id, 'doc_id': 'd1', 'sent_id': 's1', 'span': [0,1], 'confidence': 0.69},
    ]
    rels = [
        {'mention_id': 'mr1', 'predicate': 'STARTS_AT_TRL', 'subj_canonical_id': tech_id, 'subj_labels': ['Technology'], 'obj_canonical_id': trl_id, 'obj_labels': ['TRL'], 'doc_id': 'd1', 'sent_id': 's1', 'span': [2,3], 'confidence': 0.69, 'props': {'value': 8}},
    ]
    ment_e = tmp_path / 'e.jsonl'
    ment_r = tmp_path / 'r.jsonl'
    linked_p = tmp_path / 'l.jsonl'
    write_jsonl(ment_e, ents)
    write_jsonl(ment_r, rels)
    write_jsonl(linked_p, linked)
    out_dir = tmp_path / 'out'
    promote(str(ment_e), str(ment_r), str(linked_p), schema_path=schema_path_repo(), conf_thr=0.7, min_evidence=2, out_dir=str(out_dir))
    qrels = load_jsonl(out_dir / 'quarantine' / 'relations.jsonl')
    assert qrels and 'below_threshold' in qrels[0]['reasons']


def test_contract_gates(tmp_path: Path):
    tech_id = 'tech:abc'
    bad_trl_id = 'trl:0011'
    req_bad_id = 'req:bad'
    linked = [
        {'canonical_id': tech_id, 'type': 'dbo_Technology', 'labels': ['Technology'], 'key': {'uri': 'u'}, 'props': {}},
        {'canonical_id': bad_trl_id, 'type': 'kb_TRL', 'labels': ['TRL'], 'key': {'value': 11}, 'props': {}},
        {'canonical_id': req_bad_id, 'type': 'kb_Requirement', 'labels': ['Requirement'], 'key': {}, 'props': {}},
    ]
    ents = [
        {'mention_id': 'm1', 'type': 'dbo_Technology', 'labels': ['Technology'], 'surface': 't', 'canonical_id': tech_id, 'doc_id': 'd1', 'sent_id': 's1', 'span': [0,1], 'confidence': 0.9},
        {'mention_id': 'm2', 'type': 'kb_TRL', 'labels': ['TRL'], 'surface': '11', 'canonical_id': bad_trl_id, 'doc_id': 'd1', 'sent_id': 's2', 'span': [0,1], 'confidence': 0.9},
        {'mention_id': 'm3', 'type': 'kb_Requirement', 'labels': ['Requirement'], 'surface': 'R', 'canonical_id': req_bad_id, 'doc_id': 'd1', 'sent_id': 's3', 'span': [0,1], 'confidence': 0.9},
    ]
    rels = [
        {'mention_id': 'mr1', 'predicate': 'BOGUS', 'subj_canonical_id': tech_id, 'subj_labels': ['Technology'], 'obj_canonical_id': bad_trl_id, 'obj_labels': ['TRL'], 'doc_id': 'd1', 'sent_id': 's1', 'span': [0,1], 'confidence': 0.9},
        {'mention_id': 'mr2', 'predicate': 'STARTS_AT_TRL', 'subj_canonical_id': tech_id, 'subj_labels': ['Technology'], 'obj_canonical_id': bad_trl_id, 'obj_labels': ['TRL'], 'doc_id': 'd1', 'sent_id': 's2', 'span': [0,1], 'confidence': 0.9, 'props': {'value': 11}},
        {'mention_id': 'mr3', 'predicate': 'HAS_REQUIREMENT', 'subj_canonical_id': tech_id, 'subj_labels': ['Technology'], 'obj_canonical_id': req_bad_id, 'obj_labels': ['Requirement'], 'doc_id': 'd1', 'sent_id': 's3', 'span': [0,1], 'confidence': 0.9},
    ]
    ment_e = tmp_path / 'e.jsonl'
    ment_r = tmp_path / 'r.jsonl'
    linked_p = tmp_path / 'l.jsonl'
    write_jsonl(ment_e, ents)
    write_jsonl(ment_r, rels)
    write_jsonl(linked_p, linked)
    out_dir = tmp_path / 'out'
    promote(str(ment_e), str(ment_r), str(linked_p), schema_path=schema_path_repo(), conf_thr=0.7, min_evidence=1, out_dir=str(out_dir))
    qrels = load_jsonl(out_dir / 'quarantine' / 'relations.jsonl')
    reasons_sets = [set(r['reasons']) for r in qrels]
    assert any('predicate_not_allowed' in rs for rs in reasons_sets)
    assert any('type_constraint_failed' in rs for rs in reasons_sets)
    # Entities: requirement should be quarantined for missing keys
    qents = load_jsonl(out_dir / 'quarantine' / 'entities.jsonl')
    assert any(e['canonical_id'] == req_bad_id and 'missing_entity_keys' in e['reasons'] for e in qents)


def test_determinism(tmp_path: Path):
    tech_id = 'tech:abc'
    trl_id = 'trl:0008'
    linked = [
        {'canonical_id': tech_id, 'type': 'dbo_Technology', 'labels': ['Technology'], 'key': {'uri': 'u'}, 'props': {}},
        {'canonical_id': trl_id, 'type': 'kb_TRL', 'labels': ['TRL'], 'key': {'value': 8}, 'props': {}},
    ]
    ents = [
        {'mention_id': 'm1', 'type': 'dbo_Technology', 'labels': ['Technology'], 'surface': 't', 'canonical_id': tech_id, 'doc_id': 'd1', 'sent_id': 's1', 'span': [0,1], 'confidence': 0.9},
        {'mention_id': 'm2', 'type': 'dbo_Technology', 'labels': ['Technology'], 'surface': 't', 'canonical_id': tech_id, 'doc_id': 'd1', 'sent_id': 's2', 'span': [0,1], 'confidence': 0.9},
    ]
    rels = [
        {'mention_id': 'mr1', 'predicate': 'STARTS_AT_TRL', 'subj_canonical_id': tech_id, 'subj_labels': ['Technology'], 'obj_canonical_id': trl_id, 'obj_labels': ['TRL'], 'doc_id': 'd1', 'sent_id': 's1', 'span': [0,1], 'confidence': 0.9, 'props': {'value': 8}},
        {'mention_id': 'mr2', 'predicate': 'STARTS_AT_TRL', 'subj_canonical_id': tech_id, 'subj_labels': ['Technology'], 'obj_canonical_id': trl_id, 'obj_labels': ['TRL'], 'doc_id': 'd1', 'sent_id': 's2', 'span': [0,1], 'confidence': 0.9, 'props': {'value': 8}},
    ]
    ment_e = tmp_path / 'e.jsonl'
    ment_r = tmp_path / 'r.jsonl'
    linked_p = tmp_path / 'l.jsonl'
    write_jsonl(ment_e, ents)
    write_jsonl(ment_r, rels)
    write_jsonl(linked_p, linked)
    out1 = tmp_path / 'out1'
    out2 = tmp_path / 'out2'
    promote(str(ment_e), str(ment_r), str(linked_p), schema_path=schema_path_repo(), conf_thr=0.7, min_evidence=2, out_dir=str(out1))
    promote(str(ment_e), str(ment_r), str(linked_p), schema_path=schema_path_repo(), conf_thr=0.7, min_evidence=2, out_dir=str(out2))
    files = [
        'facts.entities.jsonl',
        'facts.relations.jsonl',
        os.path.join('quarantine', 'entities.jsonl'),
        os.path.join('quarantine', 'relations.jsonl'),
    ]
    for rel in files:
        p1 = out1 / rel
        p2 = out2 / rel
        assert p1.exists() and p2.exists()
        d1 = sorted(load_jsonl(p1), key=lambda x: x.get('canonical_id') or x.get('group_key'))
        d2 = sorted(load_jsonl(p2), key=lambda x: x.get('canonical_id') or x.get('group_key'))
        assert d1 == d2
