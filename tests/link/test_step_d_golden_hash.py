import hashlib
import json
import sys
from pathlib import Path
import subprocess


def sh(*args):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"cmd failed: {' '.join(args)}\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}")
    return r


def test_step_d_output_hash_matches_golden(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[2]
    fixtures = repo_root / "tests" / "fixtures"
    goldens = repo_root / "tests" / "goldens"
    outdir = tmp_path / "linked_out"
    registry = tmp_path / "registry.sqlite"

    sh(
        "combo-link",
        str(fixtures / "coref"),
        "--registry", str(registry),
        "--out", str(outdir),
        "--link-conf", "0.75",
        "--adapters", "wikidata,uei",
        "--wikidata-cache", str(fixtures / "wikidata_cache.json"),
        "--uei-cache", str(fixtures / "uei_cache.json"),
    )

    produced = outdir / "linked.entities.jsonl"
    assert produced.exists(), "linked.entities.jsonl not found"
    h = hashlib.sha256(produced.read_bytes()).hexdigest()
    golden = (goldens / "step_d_linked.entities.sha256").read_text(encoding="utf-8").strip()
    assert h == golden, f"Determinism drift:\n produced={h}\n golden=  {golden}"

    report = json.loads((outdir / "_reports" / "run_report.json").read_text(encoding="utf-8"))
    assert report.get("errors", 0) == 0

