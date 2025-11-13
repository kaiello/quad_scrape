import json
import pathlib
import subprocess
import sys
import tempfile


FIXT = pathlib.Path(__file__).with_name("fixtures")


def test_output_is_deterministic_json_serialization():
    with tempfile.TemporaryDirectory() as outdir:
        res = subprocess.run(
            ["combo-normalize", str(FIXT), "--out", outdir],
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0, res.stderr
        files = list(pathlib.Path(outdir).glob("*.normalized.json"))
        assert files
        # Pick one file and assert that re-dumping matches byte-for-byte
        p = files[0]
        txt = p.read_text(encoding="utf-8")
        obj = json.loads(txt)
        redump = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2)
        assert txt.strip() == redump.strip()

