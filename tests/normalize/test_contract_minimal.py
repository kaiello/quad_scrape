import json
import pathlib
import subprocess
import sys
import tempfile


FIXT = pathlib.Path(__file__).with_name("fixtures")


def test_minimal_contract_fields_present():
    with tempfile.TemporaryDirectory() as outdir:
        res = subprocess.run(
            [sys.executable, "-m", "combo", "normalize", str(FIXT), "--out", outdir],
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0, res.stderr
        f = next(pathlib.Path(outdir).glob("*.normalized.json"))
        data = json.loads(f.read_text(encoding="utf-8"))
        # meta
        assert data["meta"]["normalizer"]["version"]
        assert data["meta"]["doc_sha1"]
        # sentences
        s = data["sentences"][0]
        for k in ("sent_id", "page", "char_start", "char_end", "text"):
            assert k in s
        # chunks
        c = data["chunks"][0]
        for k in ("chunk_id", "sentence_ids", "text", "page_start", "page_end"):
            assert k in c
        # consecutive sentence ids
        sid_to_order = {t["sent_id"]: i for i, t in enumerate(data["sentences"])}
        ords = [sid_to_order[sid] for sid in c["sentence_ids"]]
        assert all((b - a) == 1 for a, b in zip(ords, ords[1:]))

