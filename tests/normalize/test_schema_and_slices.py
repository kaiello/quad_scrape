import pathlib
import subprocess
import tempfile
import sys


FIXT = pathlib.Path(__file__).with_name("fixtures")


def test_normalize_then_validate_passes():
    with tempfile.TemporaryDirectory() as outdir:
        res = subprocess.run(
            [sys.executable, "-m", "combo", "normalize", str(FIXT), "--out", outdir],
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0, res.stderr
        res2 = subprocess.run(
            [sys.executable, "-m", "combo", "validate", outdir],
            capture_output=True,
            text=True,
        )
        assert res2.returncode == 0, res2.stderr

