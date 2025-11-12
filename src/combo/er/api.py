from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class Entity:
    """Represents a single entity.

    Attributes:
        id: The unique ID of the entity.
        chunk_id: The ID of the chunk the entity is in.
        doc_id: The ID of the document the entity is in.
        type: The type of the entity.
        text: The text of the entity.
        start: The start character offset of the entity.
        end: The end character offset of the entity.
        conf: The confidence score of the entity.
        source_sha1: The SHA1 hash of the source document.
    """
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
    """Represents a single relation between two entities.

    Attributes:
        id: The unique ID of the relation.
        head_ent_id: The ID of the head entity.
        tail_ent_id: The ID of the tail entity.
        type: The type of the relation.
        conf: The confidence score of the relation.
        chunk_id: The ID of the chunk the relation is in.
        doc_id: The ID of the document the relation is in.
        source_sha1: The SHA1 hash of the source document.
    """
    id: str
    head_ent_id: str
    tail_ent_id: str
    type: str
    conf: float
    chunk_id: str
    doc_id: str
    source_sha1: str


def _sha16(s: str) -> str:
    """Computes the first 16 characters of the SHA1 hash of a string.

    Args:
        s: The string to hash.

    Returns:
        The first 16 characters of the SHA1 hash.
    """
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


def simple_ner(text: str, doc_id: str, chunk_id: str, source_sha1: str) -> List[Entity]:
    """A simple named entity recognition function.

    This function uses regular expressions to find emails, URLs, all-caps words,
    and capitalized words.

    Args:
        text: The text to process.
        doc_id: The ID of the document.
        chunk_id: The ID of the chunk.
        source_sha1: The SHA1 hash of the source document.

    Returns:
        A list of entities.
    """
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
    """A simple relation extraction function.

    This function links an ORG entity to the nearest URL entity that follows it.

    Args:
        entities: A list of entities.
        doc_id: The ID of the document.
        chunk_id: The ID of the chunk.
        source_sha1: The SHA1 hash of the source document.

    Returns:
        A list of relations.
    """
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


def _resolve(p: str) -> str:
    """Resolves a path to an absolute path.

    Args:
        p: The path to resolve.

    Returns:
        The absolute path.
    """
    return os.path.abspath(os.path.realpath(p))


def _load_normalized_map(norm_dir: str) -> Dict[str, Dict[str, Any]]:
    """Loads a map of normalized data from a directory of JSON files.

    This function maps chunk IDs to a dictionary containing the doc ID, text,
    source SHA1, and base filename.

    Args:
        norm_dir: The directory containing the normalized JSON files.

    Returns:
        A dictionary mapping chunk IDs to metadata.
    """
    out: Dict[str, Dict[str, Any]] = {}
    for name in os.listdir(norm_dir):
        if not name.endswith('.json'):
            continue
        path = os.path.join(norm_dir, name)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            doc_id = data.get('doc', {}).get('doc_id')
            for ch in data.get('chunks', []):
                text = ch.get('text', '')
                sha1 = hashlib.sha1((text or '').encode('utf-8')).hexdigest()
                out[ch.get('chunk_id')] = {
                    'doc_id': doc_id,
                    'text': text,
                    'source_sha1': sha1,
                    'base': os.path.splitext(name)[0],
                }
        except Exception:
            continue
    return out


def process_embedded(emb_dir: str, norm_dir: str, out_dir: str) -> Dict[str, int]:
    """Processes a directory of embedded files to extract entities and relations.

    Args:
        emb_dir: The directory containing the embedded JSONL files.
        norm_dir: The directory containing the normalized JSON files.
        out_dir: The directory to write the output to.

    Returns:
        A dictionary of counts for entities, relations, and files.
    """
    emb_dir = _resolve(emb_dir)
    norm_dir = _resolve(norm_dir)
    out_dir = _resolve(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    mapping = _load_normalized_map(norm_dir)
    counts = {'entities': 0, 'relations': 0, 'files': 0}
    for name in os.listdir(emb_dir):
        if not name.endswith('.embedded.jsonl'):
            continue
        in_path = os.path.join(emb_dir, name)
        base = os.path.splitext(name)[0]
        ents_path = os.path.join(out_dir, f"{base}.entities.jsonl")
        rels_path = os.path.join(out_dir, f"{base}.rels.jsonl")
        ents_out: List[Dict[str, Any]] = []
        rels_out: List[Dict[str, Any]] = []
        with open(in_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
                chunk_id = row.get('chunk_id')
                meta = mapping.get(chunk_id)
                if not meta:
                    continue
                doc_id = meta['doc_id']
                text = meta['text']
                src_sha1 = meta['source_sha1']
                es = simple_ner(text, doc_id, chunk_id, src_sha1)
                rs = simple_link(es, doc_id, chunk_id, src_sha1)
                for e in es:
                    ents_out.append({
                        'id': e.id, 'chunk_id': e.chunk_id, 'doc_id': e.doc_id, 'type': e.type, 'text': e.text,
                        'start': e.start, 'end': e.end, 'conf': e.conf, 'source_sha1': e.source_sha1
                    })
                for r in rs:
                    rels_out.append({
                        'id': r.id, 'head_ent_id': r.head_ent_id, 'tail_ent_id': r.tail_ent_id, 'type': r.type,
                        'conf': r.conf, 'chunk_id': r.chunk_id, 'doc_id': r.doc_id, 'source_sha1': r.source_sha1
                    })
        if ents_out:
            with open(ents_path, 'w', encoding='utf-8', newline='') as ef:
                for obj in ents_out:
                    ef.write(json.dumps(obj, ensure_ascii=False, sort_keys=True))
                    ef.write('\n')
        if rels_out:
            with open(rels_path, 'w', encoding='utf-8', newline='') as rf:
                for obj in rels_out:
                    rf.write(json.dumps(obj, ensure_ascii=False, sort_keys=True))
                    rf.write('\n')
        counts['entities'] += len(ents_out)
        counts['relations'] += len(rels_out)
        counts['files'] += 1
    # Manifest
    manifest = {**counts}
    with open(os.path.join(out_dir, 'manifest.json'), 'w', encoding='utf-8') as mf:
        json.dump(manifest, mf, ensure_ascii=False, sort_keys=True, indent=2)
    return counts
