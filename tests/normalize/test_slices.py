import json
import pathlib

from combo.normalize.api import segment_to_sentences


FIX = pathlib.Path(__file__).with_name("fixtures")


def load(name: str):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_sentence_slices_pdf_simple():
    doc = load("pdf_simple.json")
    sents = segment_to_sentences(doc)
    pages = doc["pages"]
    for s in sents:
        page_text = pages[(s.get("page") or 1) - 1]
        assert s["text"] == page_text[s["char_start"] : s["char_end"]]


def test_sentence_slices_unicode_mixed():
    doc = load("unicode_mixed.json")
    # Normalize CRLF to ensure splitter offsets are consistent with input
    doc["pages"] = [p for p in doc["pages"]]
    sents = segment_to_sentences(doc)
    pages = doc["pages"]
    for s in sents:
        page_text = pages[(s.get("page") or 1) - 1]
        assert s["text"] == page_text[s["char_start"] : s["char_end"]]

