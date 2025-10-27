import pathlib
import subprocess
import sys
import tempfile


def test_cli_normalize_runs_and_writes_files():
    fixtures = pathlib.Path(__file__).with_name("fixtures")
    with tempfile.TemporaryDirectory() as out:
        res = subprocess.run(
            [sys.executable, "-m", "combo", "normalize", str(fixtures), "--out", out],
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0, res.stderr
        outs = list(pathlib.Path(out).glob("*.normalized.json"))
        assert outs, "no normalized outputs written"

