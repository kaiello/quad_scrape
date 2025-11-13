import json
import pathlib
import tempfile
import subprocess
import sys


FIX = pathlib.Path(__file__).with_name("fixtures")


def test_array_and_object_inputs_produce_outputs():
    with tempfile.TemporaryDirectory() as out:
        res = subprocess.run(
            ["combo-normalize", str(FIX), "--out", out],
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0, res.stderr
        names = sorted([p.name for p in pathlib.Path(out).glob("*.normalized.json")])
        # Expect at least one from object_payload and multiple from array_payload
        assert any("object_payload" in n for n in names)
        assert any("array_payload.2" in n or "array_payload.1" in n for n in names)


def test_nonpdf_single_page_behavior():
    doc = json.loads((FIX / "nonpdf_simple.json").read_text(encoding="utf-8"))
    from combo.normalize.api import segment_to_sentences

    sents = segment_to_sentences(doc)
    assert all((s.get("page") or 1) == 1 for s in sents)

