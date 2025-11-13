import pathlib
import subprocess
import sys
import tempfile


def test_embed_cli_local_smoke():
    fixtures = pathlib.Path("tests/normalize/fixtures")
    with tempfile.TemporaryDirectory() as norm_out, tempfile.TemporaryDirectory() as out:
        # normalize first
        res_norm = subprocess.run(["combo-normalize", str(fixtures), "--out", norm_out
        ], capture_output=True, text=True)
        assert res_norm.returncode == 0, res_norm.stderr

        res = subprocess.run(["combo-embed", str(norm_out), "--out", out,
            "--adapter", "local", "--dim", "8", "--batch", "8", "--timeout", "5"
        ], capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
        # check one jsonl, manifest and report
        outs = list(pathlib.Path(out).glob("*.embedded.jsonl"))
        assert outs
        assert (pathlib.Path(out) / 'manifest.json').exists()
        assert (pathlib.Path(out) / '_reports' / 'run_report.json').exists()
