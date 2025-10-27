import json
import pathlib

from combo.normalize.segment import segment_to_sentences


FIX = pathlib.Path(__file__).with_name("fixtures")


def test_unicode_offsets_and_whitespace():
    doc = json.loads((FIX / "unicode_mixed.json").read_text(encoding="utf-8"))
    sents = segment_to_sentences(doc)
    pages = doc["pages"]
    for s in sents:
        page_text = pages[(s.get("page") or 1) - 1]
        # Offsets must slice back to text exactly, including emojis and combining marks
        assert s["text"] == page_text[s["char_start"] : s["char_end"]]

