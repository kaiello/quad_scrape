from __future__ import annotations

import json, os, tempfile, shutil
from combo.pipeline.promote import promote

SCHEMA = "src/combo/schema/semantic_contract.yaml"


def _write(path: str, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for ln in lines:
            f.write(ln.rstrip() + ("\n" if not ln.endswith("\n") else ""))


def test_promote_toy_bundle():
    tmp = tempfile.mkdtemp(prefix="promote_toy_")
    try:
        linked = os.path.join(tmp, "linked.entities.jsonl")
        ments_e = os.path.join(tmp, "mentions.entities.jsonl")
        ments_r = os.path.join(tmp, "mentions.relations.jsonl")

        linked_lines = [
            '{"canonical_id":"tech:railgun","type":"dbo_Technology","labels":["kb_Technology","Technology"],"key":{"uri":"http://ex/tech/railgun"},"props":{"name":"Railgun","description":"EM railgun"}}',
            '{"canonical_id":"trl:8","type":"kb_TRL","labels":["TRL"],"key":{"value":8},"props":{}}',
            '{"canonical_id":"cap:distributed_defense","type":"kb_Capability","labels":["Capability"],"key":{"name":"Distributed Defense"},"props":{"description":"Defend from multiple locations"}}',
            '{"canonical_id":"req:R-001","type":"kb_Requirement","labels":["Requirement"],"key":{"id":"R-001"},"props":{"type":"Functional","priority":"High","text":"System must support coordinated fires from multiple locations."}}',
            '{"canonical_id":"proj:PRJ-RAIL","type":"kb_Project","labels":["Project"],"key":{"code":"PRJ-RAIL"},"props":{"sponsor":"Navy","objective":"Demonstrate railgun battery"}}',
        ]
        ments_e_lines = [
            '{"mention_id":"me1","type":"dbo_Technology","labels":["kb_Technology","Technology"],"surface":"railgun","canonical_id":"tech:railgun","doc_id":"d1","sent_id":"s1","span":[0,10],"confidence":0.86,"props":{"uri":"http://ex/tech/railgun","name":"Railgun"}}',
            '{"mention_id":"me2","type":"kb_TRL","labels":["TRL"],"surface":"TRL-8","canonical_id":"trl:8","doc_id":"d1","sent_id":"s2","span":[11,20],"confidence":0.90,"props":{"value":8}}',
            '{"mention_id":"me3","type":"kb_Capability","labels":["Capability"],"surface":"distributed defense","canonical_id":"cap:distributed_defense","doc_id":"d2","sent_id":"s5","span":[5,25],"confidence":0.83,"props":{"name":"Distributed Defense"}}',
            '{"mention_id":"me4","type":"kb_Requirement","labels":["Requirement"],"surface":"R-001","canonical_id":"req:R-001","doc_id":"d3","sent_id":"s7","span":[30,40],"confidence":0.88,"props":{"id":"R-001","type":"Functional","priority":"High","text":"System must support coordinated fires from multiple locations."}}',
            '{"mention_id":"me5","type":"kb_Project","labels":["Project"],"surface":"PRJ-RAIL","canonical_id":"proj:PRJ-RAIL","doc_id":"d2","sent_id":"s4","span":[0,8],"confidence":0.82,"props":{"code":"PRJ-RAIL","objective":"Demonstrate railgun battery"}}',
        ]
        ments_r_lines = [
            '{"mention_id":"mr1","predicate":"STARTS_AT_TRL","subj_canonical_id":"tech:railgun","subj_labels":["kb_Technology","Technology"],"obj_canonical_id":"trl:8","obj_labels":["TRL"],"doc_id":"d1","sent_id":"s2","span":[50,70],"confidence":0.82,"props":{"value":8}}',
            '{"mention_id":"mr2","predicate":"STARTS_AT_TRL","subj_canonical_id":"tech:railgun","subj_labels":["kb_Technology","Technology"],"obj_canonical_id":"trl:8","obj_labels":["TRL"],"doc_id":"d2","sent_id":"s6","span":[10,30],"confidence":0.88,"props":{"value":8}}',
            '{"mention_id":"mr3","predicate":"PROVIDES_CAPABILITY","subj_canonical_id":"tech:railgun","subj_labels":["kb_Technology","Technology"],"obj_canonical_id":"cap:distributed_defense","obj_labels":["Capability"],"doc_id":"d2","sent_id":"s5","span":[0,20],"confidence":0.81,"props":{}}',
            '{"mention_id":"mr4","predicate":"PROVIDES_CAPABILITY","subj_canonical_id":"tech:railgun","subj_labels":["kb_Technology","Technology"],"obj_canonical_id":"cap:distributed_defense","obj_labels":["Capability"],"doc_id":"d3","sent_id":"s8","span":[15,33],"confidence":0.85,"props":{}}',
            '{"mention_id":"mr5","predicate":"HAS_REQUIREMENT","subj_canonical_id":"proj:PRJ-RAIL","subj_labels":["Project"],"obj_canonical_id":"req:R-001","obj_labels":["Requirement"],"doc_id":"d3","sent_id":"s7","span":[30,60],"confidence":0.87,"props":{"type":"Functional","priority":"High"}}',
            '{"mention_id":"mr6","predicate":"HAS_REQUIREMENT","subj_canonical_id":"proj:PRJ-RAIL","subj_labels":["Project"],"obj_canonical_id":"req:R-001","obj_labels":["Requirement"],"doc_id":"d4","sent_id":"s2","span":[5,22],"confidence":0.83,"props":{"type":"Functional","priority":"High"}}',
        ]

        _write(linked, linked_lines)
        _write(ments_e, ments_e_lines)
        _write(ments_r, ments_r_lines)

        out_dir = os.path.join(tmp, "facts")
        facts_entities_path, facts_relations_path, quarantine_dir = promote(
            ments_e, ments_r, linked, out_dir, SCHEMA, conf_thr=0.7, min_ev=2
        )

        ents = [json.loads(l) for l in open(facts_entities_path, encoding="utf-8")]
        rels = [json.loads(l) for l in open(facts_relations_path, encoding="utf-8")]
        qents = list(open(os.path.join(quarantine_dir, "entities.jsonl"), encoding="utf-8"))
        qrels = list(open(os.path.join(quarantine_dir, "relations.jsonl"), encoding="utf-8"))

        assert len(rels) == 3, f"expected 3 relations, got {len(rels)}"
        preds = {r["predicate"] for r in rels}
        assert {"STARTS_AT_TRL","PROVIDES_CAPABILITY","HAS_REQUIREMENT"} <= preds

        trl_rel = [r for r in rels if r["predicate"]=="STARTS_AT_TRL"][0]
        assert trl_rel["obj"]["canonical_id"] == "trl:8"
        assert trl_rel["props"].get("value") == 8

        has_req = [r for r in rels if r["predicate"]=="HAS_REQUIREMENT"][0]
        assert has_req["obj"]["canonical_id"] == "req:R-001"
        assert has_req["props"].get("type") == "Functional"
        assert has_req["props"].get("priority") == "High"

        cids = {e["canonical_id"] for e in ents}
        assert {"tech:railgun","trl:8","cap:distributed_defense","req:R-001","proj:PRJ-RAIL"} <= cids

        assert len(qents) == 0, f"unexpected entity quarantine: {qents[:1]}"
        assert len(qrels) == 0, f"unexpected relation quarantine: {qrels[:1]}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

