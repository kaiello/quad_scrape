import os, pytest

try:
    from combo.pipeline.load import load  # type: ignore
except Exception:
    pytest.skip("pipeline.load not available", allow_module_level=True)

try:
    from neo4j import GraphDatabase  # type: ignore
except Exception:
    GraphDatabase = None

from combo.pipeline.promote import promote

SCHEMA = "src/combo/schema/semantic_contract.yaml"


@pytest.mark.skipif(
    GraphDatabase is None or not os.environ.get("NEO4J_URI") or not os.environ.get("NEO4J_USER") or not os.environ.get("NEO4J_PASSWORD"),
    reason="Set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD and install neo4j driver to run integration test",
)
def test_load_into_neo4j(tmp_path):
    # Minimal smoke: reuse toy bundle
    linked = tmp_path/"linked.entities.jsonl"
    ments_e = tmp_path/"mentions.entities.jsonl"
    ments_r = tmp_path/"mentions.relations.jsonl"
    facts_dir = tmp_path/"facts"

    linked_lines = [
        '{"canonical_id":"tech:railgun","type":"dbo_Technology","labels":["kb_Technology","Technology"],"key":{"uri":"http://ex/tech/railgun"},"props":{"name":"Railgun","description":"EM railgun"}}',
        '{"canonical_id":"trl:8","type":"kb_TRL","labels":["TRL"],"key":{"value":8},"props":{}}',
        '{"canonical_id":"req:R-001","type":"kb_Requirement","labels":["Requirement"],"key":{"id":"R-001"},"props":{"type":"Functional","priority":"High","text":"System must support coordinated fires from multiple locations."}}',
        '{"canonical_id":"proj:PRJ-RAIL","type":"kb_Project","labels":["Project"],"key":{"code":"PRJ-RAIL"},"props":{"sponsor":"Navy","objective":"Demonstrate railgun battery"}}',
    ]
    ments_e_lines = [
        '{"mention_id":"me1","type":"dbo_Technology","labels":["kb_Technology","Technology"],"surface":"railgun","canonical_id":"tech:railgun","doc_id":"d1","sent_id":"s1","span":[0,10],"confidence":0.86,"props":{"uri":"http://ex/tech/railgun","name":"Railgun"}}',
        '{"mention_id":"me2","type":"kb_TRL","labels":["TRL"],"surface":"TRL-8","canonical_id":"trl:8","doc_id":"d1","sent_id":"s2","span":[11,20],"confidence":0.90,"props":{"value":8}}',
    ]
    ments_r_lines = [
        '{"mention_id":"mr1","predicate":"STARTS_AT_TRL","subj_canonical_id":"tech:railgun","subj_labels":["kb_Technology","Technology"],"obj_canonical_id":"trl:8","obj_labels":["TRL"],"doc_id":"d1","sent_id":"s2","span":[50,70],"confidence":0.82,"props":{"value":8}}',
    ]
    linked.write_text("\n".join(linked_lines)+"\n", encoding="utf-8")
    ments_e.write_text("\n".join(ments_e_lines)+"\n", encoding="utf-8")
    ments_r.write_text("\n".join(ments_r_lines)+"\n", encoding="utf-8")

    promote(str(ments_e), str(ments_r), str(linked), str(facts_dir), SCHEMA, conf_thr=0.7, min_ev=1)

    # If load is implemented, this will import and execute; otherwise this test remains skipped
    load(
        str(facts_dir),
        os.environ["NEO4J_URI"],
        os.environ["NEO4J_USER"],
        os.environ["NEO4J_PASSWORD"],
        batch=1000,
    )

