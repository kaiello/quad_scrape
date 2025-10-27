import json
import pathlib
import subprocess
import sys
import tempfile


def test_how_things_grouping_and_min_count():
    with tempfile.TemporaryDirectory() as wd:
        wd = pathlib.Path(wd)
        er = wd / "er"; er.mkdir()
        # Mentions: same entity id collapses; plural/singular normalized when no IDs
        ents = [
            {"doc_id":"d1","chunk_id":"c1","type":"DEVICE","text":"railgun prototype","mention_id":"m1","resolved_entity_id":"E_DEV"},
            {"doc_id":"d1","chunk_id":"c1","type":"DEVICE","text":"the railgun prototypes","mention_id":"m2","resolved_entity_id":"E_DEV"},
            {"doc_id":"d1","chunk_id":"c1","type":"BOAT","text":"boat","mention_id":"m3"},
            {"doc_id":"d1","chunk_id":"c1","type":"BOAT","text":"boats","mention_id":"m4"},
            {"doc_id":"d1","chunk_id":"c1","type":"OTHER","text":"unknown gadget","mention_id":"m5"},
        ]
        (er/"sample.entities.jsonl").write_text("\n".join(json.dumps(e) for e in ents)+"\n", encoding="utf-8")

        out = wd / "fourw"
        res = subprocess.run([
            sys.executable, "-m", "combo", "fourw", str(er), "--out", str(out),
            "--things-labels", "DEVICE,BOAT", "--min-thing-count", "1",
        ], capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
        dp = json.loads((out/"sample.docprops.jsonl").read_text(encoding="utf-8").splitlines()[0])
        things = dp["how"]["things"]
        # Expect 2 groups: E_DEV collapsed, and boat/boats collapsed by name normalization
        assert len(things) == 2
        names = sorted([t["name"].lower() for t in things])
        assert any("railgun" in n for n in names)
        assert any("boat" in n for n in names)
        assert dp["stats"]["things"] == 2

        # Test allow_other_into_how and min count filter
        out2 = wd / "fourw2"
        res2 = subprocess.run([
            sys.executable, "-m", "combo", "fourw", str(er), "--out", str(out2),
            "--allow-other-into-how", "--min-thing-count", "2",
        ], capture_output=True, text=True)
        assert res2.returncode == 0, res2.stderr
        dp2 = json.loads((out2/"sample.docprops.jsonl").read_text(encoding="utf-8").splitlines()[0])
        things2 = dp2["how"]["things"]
        # With min count 2, boat/boats collapsed remains; unknown gadget (count 1) excluded unless threshold 1
        assert all(t["count"] >= 2 for t in things2)

