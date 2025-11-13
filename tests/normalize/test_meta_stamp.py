import glob
import json
import pathlib
import subprocess
import sys
import tempfile


FIXT = pathlib.Path(__file__).with_name("fixtures")


def test_meta_has_version_and_checksum():
    with tempfile.TemporaryDirectory() as outdir:
        res = subprocess.run(
            ["combo-normalize", str(FIXT), "--out", outdir],
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0, res.stderr
        files = glob.glob(str(pathlib.Path(outdir) / "*.normalized.json"))
        assert files, "no outputs"
        sample = json.loads(pathlib.Path(files[0]).read_text(encoding="utf-8"))
        meta = sample["meta"]
        assert meta["normalizer"]["name"] == "combo.segment"
        assert meta["normalizer"]["version"]
        assert len(meta["doc_sha1"]) == 40

