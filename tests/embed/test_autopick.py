import os
from combo.embed.api import select_gguf


def test_select_gguf_prefers_bge_and_smallest(tmp_path):
    # Create fake gguf files with different names/sizes
    p1 = tmp_path / "modelA.gguf"
    p2 = tmp_path / "bge-small.gguf"
    p3 = tmp_path / "nomic-large.gguf"
    p1.write_bytes(b"x" * 300)
    p2.write_bytes(b"x" * 100)  # preferred by name and smallest
    p3.write_bytes(b"x" * 200)

    picked = select_gguf(str(tmp_path))
    assert os.path.basename(picked) == "bge-small.gguf"

