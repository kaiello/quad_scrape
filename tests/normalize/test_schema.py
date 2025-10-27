import json
import pathlib

from combo.normalize.segment import segment_to_sentences, build_chunks
from combo.normalize.validate import validate_normalized_object


FIX = pathlib.Path(__file__).with_name("fixtures")


def test_schema_minimal_valid():
    doc = json.loads((FIX / "pdf_simple.json").read_text(encoding="utf-8"))
    sents = segment_to_sentences(doc)
    chunks = build_chunks(sents, doc_id=doc["doc_id"], max_tokens=512)
    normalized = {
        "meta": {
            "normalizer": {"name": "combo.segment", "version": "0.1.0", "spec": "v1"},
            "doc_sha1": "x" * 40,
            "n_sentences": len(sents),
            "n_chunks": len(chunks),
        },
        "doc": {"doc_id": doc["doc_id"], "source_path": doc["source_path"], "num_pages": len(doc["pages"]), "pages": doc["pages"]},
        "sentences": sents,
        "chunks": chunks,
        "images": doc.get("images", []),
    }
    errs = validate_normalized_object(normalized)
    assert not errs, f"unexpected schema/invariant errors: {errs}"
