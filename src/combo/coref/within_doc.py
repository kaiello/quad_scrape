from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple


PRONOUNS = {
    "it": ("singular", "neut"),
    "this": ("singular", "neut"),
    "that": ("singular", "neut"),
    "he": ("singular", "masc"),
    "she": ("singular", "fem"),
    "him": ("singular", "masc"),
    "her": ("singular", "fem"),
    "they": ("plural", "unknown"),
    "them": ("plural", "unknown"),
    "these": ("plural", "neut"),
    "those": ("plural", "neut"),
}


DEVICE_LIKE_WORDS = {
    "drone",
    "system",
    "device",
    "battery",
    "pack",
    "railgun",
    "prototype",
}

FEMALE_NAMES = {
    "jane", "alice", "mary", "anna", "susan", "kate", "karen", "linda",
}
MALE_NAMES = {
    "bob", "john", "michael", "tom", "david", "peter", "paul",
}


def _derive_mention_features(m: Dict) -> Dict:
    t = (m.get("text") or "").strip()
    low = t.lower()
    is_pron = low in PRONOUNS
    number = m.get("number") or (PRONOUNS[low][0] if is_pron else "unknown")
    gender = m.get("gender") or (PRONOUNS[low][1] if is_pron else "unknown")
    # Simple name-based gender hint for PERSON
    if (m.get("type") or "").upper() == "PERSON" and gender == "unknown" and not is_pron:
        if low in FEMALE_NAMES:
            gender = "fem"
        elif low in MALE_NAMES:
            gender = "masc"
    return {
        **m,
        "is_pronoun": bool(m.get("is_pronoun", is_pron)),
        "pronoun_form": m.get("pronoun_form") if m.get("pronoun_form") is not None else (low if is_pron else None),
        "number": number,
        "gender": gender,
        "sent_id": m.get("sent_id", 0),
        "mention_id": m.get("mention_id") or f"{m.get('doc_id')}:{m.get('chunk_id')}:{m.get('start')}-{m.get('end')}",
    }


def _estimate_number_for_candidate(c: Dict) -> str:
    # Heuristic: ORG -> singular; words ending with 's' (non-ORG) -> plural
    txt = (c.get("text") or "").strip()
    if (c.get("type") or "").upper() == "ORG":
        return "singular"
    if txt.lower() in {"they", "these", "those"}:
        return "plural"
    if len(txt) > 3 and txt.endswith("s"):
        return "plural"
    return "singular"


def _is_device_like(c: Dict) -> bool:
    ty = (c.get("type") or "").upper()
    txt = (c.get("text") or "").lower()
    return ty in {"PRODUCT", "DEVICE"} or any(w in txt for w in DEVICE_LIKE_WORDS)


def resolve_coref(
    ents: List[Dict],
    max_sent_back: int = 3,
    max_mentions_back: int = 30,
) -> List[Dict]:
    """Return a new list with coref fields populated.

    Uses deterministic nearest-antecedent heuristics:
    - Pronoun agreement on number/gender where available
    - Prefer device/product over org for it/this/that
    - Plural pronouns prefer plural-like candidates
    """
    aug = [_derive_mention_features(e) for e in ents]
    # Keep original order; create an index for lookup
    out: List[Dict] = []
    for i, m in enumerate(aug):
        m2 = dict(m)
        m2.update({
            "antecedent_mention_id": None,
            "resolved_entity_id": None,
            "coref_rule": "unresolved",
            "coref_conf": 0.0,
        })
        if not m2.get("is_pronoun"):
            out.append(m2)
            continue
        # Look back
        candidates: List[Tuple[int, Dict]] = []
        cur_sent = int(m2.get("sent_id") or 0)
        back_count = 0
        j = i - 1
        while j >= 0 and back_count < max_mentions_back:
            c = aug[j]
            if abs(cur_sent - int(c.get("sent_id") or 0)) <= max_sent_back:
                candidates.append((j, c))
                back_count += 1
            j -= 1

        form = (m2.get("pronoun_form") or "").lower()
        num = m2.get("number") or "unknown"
        gen = m2.get("gender") or "unknown"
        chosen: Optional[Dict] = None
        rule = "unresolved"
        conf = 0.0

        # Filter candidates by basic agreement
        def compatible(c: Dict) -> bool:
            # Gender agreement only for he/she/him/her
            if form in {"he", "him"} and (c.get("gender", "unknown") not in {"masc", "unknown"}):
                return False
            if form in {"she", "her"} and (c.get("gender", "unknown") not in {"fem", "unknown"}):
                return False
            # Number agreement
            if num == "plural" and _estimate_number_for_candidate(c) != "plural":
                return False
            if num == "singular" and _estimate_number_for_candidate(c) != "singular":
                return False
            return True

        compat = [(idx, c) for idx, c in candidates if compatible(c)]

        # Device-over-org preference for it/this/that
        if form in {"it", "this", "that"}:
            dev_first = [(idx, c) for idx, c in compat if _is_device_like(c)]
            if dev_first:
                chosen = dev_first[0][1]
                rule = "prefer_device_over_org"
                conf = 0.85
            elif compat:
                chosen = compat[0][1]
                rule = "nearest_compatible"
                conf = 0.75
        else:
            if compat:
                chosen = compat[0][1]
                rule = "nearest_compatible"
                conf = 0.75 if num == "singular" else 0.7

        if chosen is not None:
            m2["antecedent_mention_id"] = chosen.get("mention_id")
            # Prefer upstream entity id if present, else antecedent mention_id
            m2["resolved_entity_id"] = chosen.get("id") or chosen.get("mention_id")
            m2["coref_rule"] = rule
            m2["coref_conf"] = conf
        out.append(m2)
    return out
