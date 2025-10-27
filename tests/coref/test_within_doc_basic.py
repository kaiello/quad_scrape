from __future__ import annotations

from combo.coref.within_doc import resolve_coref


def mk(doc_id, chunk_id, text, start, end, typ="PERSON", sent_id=0):
    return {"doc_id": doc_id, "chunk_id": chunk_id, "text": text, "start": start, "end": end, "type": typ, "sent_id": sent_id}


def test_personal_pronouns_map_to_latest_compatible():
    # Jane met Bob. She thanked him.
    ents = [
        mk("d1", "c1", "Jane", 0, 4, "PERSON", 0),
        mk("d1", "c1", "Bob", 10, 13, "PERSON", 0),
        mk("d1", "c1", "She", 15, 18, "PERSON", 1),
        mk("d1", "c1", "him", 25, 28, "PERSON", 1),
    ]
    out = resolve_coref(ents)
    she = out[2]
    him = out[3]
    assert she.get("antecedent_mention_id") == out[0].get("mention_id")
    assert him.get("antecedent_mention_id") == out[1].get("mention_id")


def test_device_preferred_over_org_for_it():
    # ACME released a drone. It supports swarming.
    ents = [
        mk("d2", "c1", "ACME", 0, 4, "ORG", 0),
        mk("d2", "c1", "drone", 16, 21, "PRODUCT", 0),
        mk("d2", "c1", "It", 24, 26, "PERSON", 1),
    ]
    out = resolve_coref(ents)
    it = out[2]
    assert it.get("antecedent_mention_id") == out[1].get("mention_id")
    assert it.get("coref_rule") == "prefer_device_over_org"


def test_plural_agreement():
    # The battery packs are modular. They charge fast.
    ents = [
        mk("d3", "c1", "battery packs", 4, 17, "PRODUCT", 0),
        mk("d3", "c1", "They", 24, 28, "PERSON", 1),
    ]
    out = resolve_coref(ents)
    they = out[1]
    assert they.get("antecedent_mention_id") == out[0].get("mention_id")

