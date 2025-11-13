import json
import pathlib
import subprocess
import sys
import tempfile


def test_link_end_to_end_and_sorted():
    with tempfile.TemporaryDirectory() as wd:
        wd = pathlib.Path(wd)
        coref = wd / "coref"; coref.mkdir()
        ents = [
            {"doc_id":"d1","type":"PERSON","text":"Jane","mention_id":"m1","resolved_entity_id":"E_JANE"},
            {"doc_id":"d1","type":"PERSON","text":"She","mention_id":"m2","resolved_entity_id":"E_JANE"},
            {"doc_id":"d1","type":"ORG","text":"ACME","mention_id":"m3","resolved_entity_id":"E_ACME"},
            {"doc_id":"d2","type":"ORG","text":"ACME","mention_id":"m4","resolved_entity_id":"E_ACME"},
        ]
        (coref/"a.entities.jsonl").write_text("\n".join(json.dumps(e) for e in ents)+"\n", encoding="utf-8")

        out = wd / "linked"
        db = wd / "registry.sqlite"
        res = subprocess.run(["combo-link", str(coref), "--registry", str(db), "--out", str(out)], capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
        linked_path = out / "linked.entities.jsonl"
        assert linked_path.exists()
        lines = linked_path.read_text(encoding="utf-8").splitlines()
        # Deterministic ordering: by doc_id, type, canonical_id
        assert lines == sorted(lines)

