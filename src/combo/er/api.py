from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class Entity:
    id: str
    chunk_id: str
    doc_id: str
    type: str
    text: str
    start: int
    end: int
    conf: float
    source_sha1: str


@dataclass
class Relation:
    id: str
    head_ent_id: str
    tail_ent_id: str
    type: str
    conf: float
    chunk_id: str
    doc_id: str
    source_sha1: str


def _sha16(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


def simple_ner(text: str, doc_id: str, chunk_id: str, source_sha1: str) -> List[Entity]:
    ents: List[Entity] = []
    # Patterns: emails, urls, ALLCAPS words (ORG-ish), Capitalized words (PERSON-ish)
    email_pat = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    url_pat = re.compile(r"https?://\S+|www\.\S+")
    allcaps_pat = re.compile(r"\b[A-Z]{2,}\b")
    proper_pat = re.compile(r"\b[A-Z][a-z]+\b")

    def _add(span: Tuple[int, int], etype: str):
        a, b = span
        t = text[a:b]
        eid = _sha16(f"{doc_id}|{chunk_id}|{a}|{b}|{t}")
        ents.append(Entity(
            id=eid, chunk_id=chunk_id, doc_id=doc_id, type=etype, text=t, start=a, end=b, conf=0.8, source_sha1=source_sha1
        ))

    for m in email_pat.finditer(text):
        _add((m.start(), m.end()), "EMAIL")
    for m in url_pat.finditer(text):
        _add((m.start(), m.end()), "URL")
    for m in allcaps_pat.finditer(text):
        _add((m.start(), m.end()), "ORG")
    for m in proper_pat.finditer(text):
        _add((m.start(), m.end()), "PERSON")

    # Deduplicate by (start,end,type)
    seen = set()
    uniq: List[Entity] = []
    for e in sorted(ents, key=lambda e: (e.start, e.end, e.type)):
        key = (e.start, e.end, e.type)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(e)
    return uniq


def simple_link(entities: List[Entity], doc_id: str, chunk_id: str, source_sha1: str) -> List[Relation]:
    rels: List[Relation] = []
    # Toy rule: connect an ORG followed by a URL within the chunk
    urls = [e for e in entities if e.type == "URL"]
    orgs = [e for e in entities if e.type == "ORG"]
    for o in orgs:
        # find nearest URL after org
        after = [u for u in urls if u.start > o.end]
        if after:
            u = after[0]
            rid = _sha16(f"{doc_id}|{chunk_id}|{o.id}|{u.id}|HAS_LINK")
            rels.append(Relation(id=rid, head_ent_id=o.id, tail_ent_id=u.id, type="HAS_LINK", conf=0.6, chunk_id=chunk_id, doc_id=doc_id, source_sha1=source_sha1))
    return rels

