import json
import pathlib

from combo.normalize.api import segment_to_sentences, build_chunks


FIX = pathlib.Path(__file__).with_name("fixtures")


def load(name: str):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_determinism_ids_pdf_simple():
    doc = load("pdf_simple.json")
    s1 = segment_to_sentences(doc)
    s2 = segment_to_sentences(doc)
    # same order & same ids
    assert [(s["sent_id"], s["char_start"], s["char_end"]) for s in s1] == [
        (s["sent_id"], s["char_start"], s["char_end"]) for s in s2
    ]

    c1 = build_chunks(s1, doc_id=doc["doc_id"], max_tokens=512)
    c2 = build_chunks(s2, doc_id=doc["doc_id"], max_tokens=512)
    assert [(c["chunk_id"], tuple(c["sentence_ids"])) for c in c1] == [
        (c["chunk_id"], tuple(c["sentence_ids"])) for c in c2
    ]


def test_sent_id_changes_when_boundary_changes():
    base = load("pdf_simple.json")
    sents = segment_to_sentences(base)
    assert len(sents) >= 2
    # Nudge first sentence boundary by +1 char (simulate splitter change)
    first = sents[0]
    doc_mod = load("pdf_simple.json")
    txt0 = doc_mod["pages"][0]
    # shift start forward by 1
    new_start = first["char_start"] + 1
    doc_mod["pages"][0] = txt0[new_start: first["char_end"]] + txt0[first["char_end"]:]
    sents_mod = segment_to_sentences(doc_mod)
    assert sents_mod[0]["sent_id"] != first["sent_id"]


def test_doc_id_change_changes_sent_ids():
    base = load("pdf_simple.json")
    s1 = segment_to_sentences(base)
    base2 = dict(base)
    base2["doc_id"] = "another-doc-id"
    s2 = segment_to_sentences(base2)
    assert [s["sent_id"] for s in s1] != [s["sent_id"] for s in s2]

