import json
import pathlib
import subprocess
import sys
import tempfile


def test_fourw_basic_grouping_and_report():
    with tempfile.TemporaryDirectory() as wd:
        wd = pathlib.Path(wd)
        # Build ER dir with coref-like entities
        er = wd / "er"; er.mkdir()
        # One doc base
        ents = [
            {"doc_id":"d1","chunk_id":"c1","type":"PERSON","text":"Jane","start":0,"end":4,"mention_id":"m1"},
            {"doc_id":"d1","chunk_id":"c1","type":"PERSON","text":"She","start":10,"end":13,"mention_id":"m2","is_pronoun":True,"antecedent_mention_id":"m1","resolved_entity_id":"E_JANE"},
            {"doc_id":"d1","chunk_id":"c1","type":"ORG","text":"ACME","start":20,"end":24,"mention_id":"m3","resolved_entity_id":"E_ACME"},
            {"doc_id":"d1","chunk_id":"c1","type":"DATE","text":"2024","start":30,"end":34,"mention_id":"m4"},
            {"doc_id":"d1","chunk_id":"c1","type":"GPE","text":"Austin","start":40,"end":46,"mention_id":"m5"},
        ]
        (er/"sample.entities.jsonl").write_text("\n".join(json.dumps(e) for e in ents)+"\n", encoding="utf-8")

        # Normalized dir with meta (filename infers doc_type)
        norm = wd / "norm"; norm.mkdir()
        norm_obj = {"doc": {"doc_id":"d1", "source_path":"report.pdf", "num_pages":1, "pages":["Preview 2024"]}, "meta": {"doc_sha1":"x"*40}}
        (norm/"sample.normalized.json").write_text(json.dumps(norm_obj), encoding="utf-8")

        out = wd / "fourw"
        res = subprocess.run(["combo-fourw", str(er), "--out", str(out), "--normalized-dir", str(norm)], capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
        # Read docprops
        dp_path = out/"sample.docprops.jsonl"
        assert dp_path.exists()
        dp = json.loads(dp_path.read_text(encoding="utf-8").splitlines()[0])
        assert dp["who"]["people"][0]["name"] == "Jane"
        assert dp["what"]["doc_type"] == "pdf"
        assert any(w["value"] == "2024" for w in dp["when"])
        assert any(w["name"] == "Austin" for w in dp["where"])
        # Report exists
        rep = json.loads((out/"_reports"/"run_report.json").read_text(encoding="utf-8"))
        assert rep["docs"] == 1
        assert rep["totals"]["persons"] >= 1

