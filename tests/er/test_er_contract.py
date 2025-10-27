import json
import pathlib
import subprocess
import sys
import tempfile


def test_er_pipeline_minimal():
    with tempfile.TemporaryDirectory() as wd:
        wd = pathlib.Path(wd)
        # Create minimal normalized with one chunk
        norm_dir = wd / "norm"
        norm_dir.mkdir()
        text = "ACME visited https://example.com and emailed JOHN@EXAMPLE.COM"
        doc_id = "D1"
        chunk_id = "C1"
        norm_obj = {
            "doc": {"doc_id": doc_id, "source_path": "x", "num_pages": 1, "pages": [text]},
            "chunks": [{"doc_id": doc_id, "chunk_id": chunk_id, "text": text, "sentence_ids": [], "page_start": 1, "page_end": 1}],
            "sentences": [],
            "images": []
        }
        (norm_dir / "sample.normalized.json").write_text(json.dumps(norm_obj), encoding="utf-8")

        # Create corresponding embedded jsonl with matching chunk_id
        emb_dir = wd / "emb"
        emb_dir.mkdir()
        emb_row = {"doc_id": doc_id, "chunk_id": chunk_id, "model": "local", "dim": 4, "embedding": [0,0,0,0], "text_sha1": "x"*40}
        (emb_dir / "sample.normalized.embedded.jsonl").write_text(json.dumps(emb_row)+"\n", encoding="utf-8")

        out_dir = wd / "er"
        res = subprocess.run([sys.executable, "-m", "combo", "er", str(emb_dir), "--normalized-dir", str(norm_dir), "--out", str(out_dir)], capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
        ents = list(out_dir.glob("*.entities.jsonl"))
        rels = list(out_dir.glob("*.rels.jsonl"))
        assert ents, "no entities output"
        # Entities should contain EMAIL and URL at least
        content = ents[0].read_text(encoding="utf-8")
        assert "EMAIL" in content and "URL" in content
        # Manifest exists
        assert (out_dir / "manifest.json").exists()

