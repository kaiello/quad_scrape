import subprocess
import sys


def test_cli_help_and_validate_usage():
    res = subprocess.run(["combo"], capture_output=True, text=True)
    assert res.returncode != 0

    res2 = subprocess.run(["combo-normalize", "--help"], capture_output=True, text=True)
    assert res2.returncode in (0,)

    res3 = subprocess.run(["combo-validate"], capture_output=True, text=True)
    # argparse missing arg returns 2
    assert res3.returncode in (2,)

