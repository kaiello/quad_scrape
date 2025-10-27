import json
import pathlib

from combo.normalize.segment import segment_to_sentences, build_chunks


FIX = pathlib.Path(__file__).with_name("fixtures")


def load(name: str):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_chunks_consecutive_and_token_budget():
    doc = load("pdf_cross_page.json")
    sents = segment_to_sentences(doc)
    chunks = build_chunks(sents, doc_id=doc["doc_id"], max_tokens=20)
    # map sentence_id -> index
    order = {s["sent_id"]: i for i, s in enumerate(sents)}
    for ch in chunks:
        # consecutive sentence ids
        ords = [order[sid] for sid in ch["sentence_ids"]]
        assert all((b - a) == 1 for a, b in zip(ords, ords[1:])), "non-consecutive sentences in chunk"
        # token budget
        assert len(ch["text"].split()) <= 20
        # page range reflects min/max
        pages = [sents[order[sid]]["page"] for sid in ch["sentence_ids"]]
        if pages:
            pmin = min(p for p in pages if p is not None)
            pmax = max(p for p in pages if p is not None)
            assert ch["page_start"] in (None, pmin)
            assert ch["page_end"] in (None, pmax)

