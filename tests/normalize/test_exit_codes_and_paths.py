import pathlib
import subprocess
import sys
import tempfile


def test_validate_malformed_json_returns_2():
    with tempfile.TemporaryDirectory() as tmp:
        bad = pathlib.Path(tmp) / "bad.normalized.json"
        bad.write_text("{ not: valid json }", encoding="utf-8")
        res = subprocess.run(["combo-validate", str(bad)], capture_output=True, text=True)
        assert res.returncode == 2
        assert "failed to read/parse" in (res.stdout + res.stderr)


def test_outdir_inside_indir_is_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        in_dir = pathlib.Path(tmp) / "in"
        out_dir = in_dir / "subout"
        in_dir.mkdir()
        out_dir.mkdir()
        # minimal valid extracted payload to trigger processing
        (in_dir / "doc.json").write_text('{"doc_id":"x","source_path":"x","pages":["A."],"images":[]}', encoding="utf-8")
        res = subprocess.run(
            ["combo-normalize", str(in_dir), "--out", str(out_dir)],
            capture_output=True,
            text=True,
        )
        assert res.returncode == 2
        assert "must not be inside the input" in (res.stdout + res.stderr)

