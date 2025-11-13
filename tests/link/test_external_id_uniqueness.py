import json
import pathlib
import sqlite3
import subprocess
import sys
import tempfile


def test_external_ids_unique_per_source():
    with tempfile.TemporaryDirectory() as wd:
        wd = pathlib.Path(wd)
        coref = wd / "coref"; coref.mkdir()
        ents = [
            {"doc_id":"d1","type":"ORG","text":"ACME","mention_id":"m1"},
            {"doc_id":"d1","type":"ORG","text":"Acme","mention_id":"m2"},
        ]
        (coref/"orgs.entities.jsonl").write_text("\n".join(json.dumps(e) for e in ents)+"\n", encoding="utf-8")
        cache = wd / "wikidata.json"
        cache.write_text(json.dumps({"acme": "Q123"}), encoding="utf-8")
        out = wd / "linked"; db = wd / "registry.sqlite"
        res = subprocess.run(["combo-link", str(coref), "--registry", str(db), "--out", str(out), "--adapters", "wikidata", "--wikidata-cache", str(cache)], capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
        con = sqlite3.connect(str(db))
        cur = con.execute("SELECT COUNT(*) FROM external_ids WHERE source='wikidata' AND external_id='Q123'")
        n = cur.fetchone()[0]
        con.close()
        assert n == 1
