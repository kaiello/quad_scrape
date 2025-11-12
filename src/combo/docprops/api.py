from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Tuple


MIME_MAP: Dict[str, str] = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "presentation",
    "application/vnd.ms-powerpoint": "presentation",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "document",
    "application/msword": "document",
    "text/plain": "text",
}

DATE_PATTERNS = [
    re.compile(r" (20\d{2}|19\d{2})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01]) "),
    re.compile(r" (jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},\s*(20\d{2}|19\d{2}) ", re.I),
    re.compile(r" (20\d{2}|19\d{2}) "),
]

# Labels considered "things" (for HOW) by default
DEFAULT_THINGS = {
    "DEVICE","PRODUCT","EQUIPMENT","VEHICLE","WEAPON","SYSTEM","PLATFORM","TOOL",
    "SOFTWARE","HARDWARE","COMPONENT","MATERIAL","SENSOR","PAYLOAD","AIRCRAFT","VESSEL",
    "SHIP","BOAT","UAV","UAS","DRONE","SATELLITE","MISSILE","PROTOTYPE","MODEL",
    "ALGORITHM","METHOD","PROCESS",
}


_DET_RE = re.compile(r"^(the|a|an)\s+", re.I)


def _normalize_name(text: str) -> str:
    """Normalizes a name by stripping determiners and making it lowercase.

    Args:
        text: The name to normalize.

    Returns:
        The normalized name.
    """
    t = (text or "").strip()
    t = _DET_RE.sub("", t)  # strip leading determiners
    low = t.lower()
    # simple plural→singular heuristics
    if low.endswith("ies") and len(low) > 3:
        low = low[:-3] + "y"
    elif low.endswith("ses") and len(low) > 3:
        low = low[:-2]  # reduce 'ses'→'s'
    elif low.endswith("s") and not low.endswith("ss"):
        low = low[:-1]
    return low


def _resolve(path: str) -> str:
    """Resolves a path to an absolute path.

    Args:
        path: The path to resolve.

    Returns:
        The absolute path.
    """
    return os.path.abspath(os.path.realpath(path))


def _doc_type(meta: Dict[str, Any]) -> Optional[str]:
    """Determines the document type from metadata.

    Args:
        meta: The document metadata.

    Returns:
        The document type, or None if it cannot be determined.
    """
    mime = (meta or {}).get("mime")
    if mime and mime in MIME_MAP:
        return MIME_MAP[mime]
    fn = ((meta or {}).get("filename") or "").lower()
    if fn.endswith(".pdf"):
        return "pdf"
    if fn.endswith((".ppt", ".pptx")):
        return "presentation"
    if fn.endswith((".doc", ".docx")):
        return "document"
    if fn.endswith(".txt"):
        return "text"
    return None


def _iter_entities_from_dir(base_dir: str) -> Iterable[Tuple[str, Dict[str, Any]]]:
    """Iterates over entities from a directory of JSONL files.

    Args:
        base_dir: The directory to read from.

    Yields:
        A tuple of the document base name and the entity.
    """
    for name in os.listdir(base_dir):
        if not name.endswith('.entities.jsonl'):
            continue
        doc_base = os.path.splitext(name)[0]
        if doc_base.endswith('.entities'):
            doc_base = doc_base[:-9]
        path = os.path.join(base_dir, name)
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                yield doc_base, json.loads(line)


def _load_doc_meta_map(normalized_dir: Optional[str]) -> Dict[str, Dict[str, Any]]:
    """Loads a map of document metadata from a directory of JSON files.

    Args:
        normalized_dir: The directory to read from.

    Returns:
        A dictionary mapping document IDs to metadata.
    """
    if not normalized_dir:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for name in os.listdir(normalized_dir):
        if not name.endswith('.json'):
            continue
        path = os.path.join(normalized_dir, name)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            doc = data.get('doc', {})
            src = (doc.get('source_path') or '')
            meta = {
                'doc_id': doc.get('doc_id') or data.get('doc_id'),
                'filename': os.path.basename(src) if src else None,
                'mime': None,
                'text_preview': (data.get('doc', {}).get('pages') or [''])[0],
                'source_sha1': data.get('meta', {}).get('doc_sha1'),
            }
            if meta['doc_id']:
                out[meta['doc_id']] = meta
        except Exception:
            continue
    return out


def build_doc_props(
    mentions: List[Dict[str, Any]],
    *,
    doc_meta: Optional[Dict[str, Any]] = None,
    max_fallback_dates: int = 5,
    things_labels: Optional[set[str]] = None,
    min_thing_count: int = 1,
    allow_other_into_how: bool = False,
) -> Dict[str, Any]:
    """Builds a dictionary of document properties from a list of mentions.

    This function aggregates mentions into categories (who, what, when, where,
    how) to provide a summary of the document's contents.

    Args:
        mentions: A list of mentions to process.
        doc_meta: Optional metadata for the document.
        max_fallback_dates: The maximum number of dates to extract from the
            text preview if no date mentions are found.
        things_labels: A set of labels to consider as "things" for the "how"
            category.
        min_thing_count: The minimum number of times a thing must be mentioned
            to be included in the "how" category.
        allow_other_into_how: Whether to include mentions with the "OTHER"
            label in the "how" category.

    Returns:
        A dictionary of document properties.
    """
    mentions = list(mentions or [])
    if not mentions and not doc_meta:
        return {}
    doc_id = (mentions[0].get('doc_id') if mentions else (doc_meta or {}).get('doc_id'))
    src_sha1 = (mentions[0].get('source_sha1') if mentions else None) or (doc_meta or {}).get('source_sha1')

    def key_for(m: Dict[str, Any]) -> str:
        return m.get('resolved_entity_id') or m.get('entity_id') or m.get('mention_id') or (m.get('text') or '').lower()

    people: Dict[str, Dict[str, Any]] = {}
    orgs: Dict[str, Dict[str, Any]] = {}
    whens: List[Dict[str, Any]] = []
    wheres: List[Dict[str, Any]] = []
    things_map: Dict[str, Dict[str, Any]] = {}

    tlabels = {lab.upper() for lab in (things_labels or DEFAULT_THINGS)}

    for m in mentions:
        lab = (m.get('label') or m.get('type') or '').upper()
        if lab == 'PERSON':
            k = key_for(m)
            slot = people.setdefault(k, {"name": m.get('text'), "entity_id": m.get('resolved_entity_id') or m.get('entity_id'), "count": 0, "mention_ids": []})
            slot['count'] += 1
            slot['mention_ids'].append(m.get('mention_id'))
        elif lab == 'ORG':
            k = key_for(m)
            slot = orgs.setdefault(k, {"name": m.get('text'), "entity_id": m.get('resolved_entity_id') or m.get('entity_id'), "count": 0, "mention_ids": []})
            slot['count'] += 1
            slot['mention_ids'].append(m.get('mention_id'))
        elif lab in {'GPE', 'LOCATION', 'FACILITY'}:
            wheres.append({"name": m.get('text'), "type": lab, "mention_ids": [m.get('mention_id')]})
        elif lab in {'DATE', 'TIME'}:
            whens.append({"value": m.get('normalized') or m.get('text'), "grain": m.get('grain') or 'unknown', "mention_ids": [m.get('mention_id')]})
        elif lab in tlabels or (allow_other_into_how and lab == 'OTHER'):
            # Group things
            name = m.get('text') or ''
            # Prefer stable IDs; if missing, fall back to normalized surface form before mention_id to collapse plural/singular
            k = m.get('resolved_entity_id') or m.get('entity_id') or _normalize_name(name) or m.get('mention_id')
            slot = things_map.setdefault(k, {
                'name': name,
                'class': lab,
                'entity_id': m.get('resolved_entity_id') or m.get('entity_id'),
                'count': 0,
                'mention_ids': [],
            })
            slot['count'] += 1
            slot['mention_ids'].append(m.get('mention_id'))

    # Fallback date scan
    if not whens and (doc_meta or {}).get('text_preview'):
        found = 0
        tp = doc_meta['text_preview']  # type: ignore[index]
        for pat in DATE_PATTERNS:
            for mt in pat.finditer(tp):
                val = mt.group(0)
                whens.append({"value": val, "grain": 'year' if len(val) == 4 else 'day', "mention_ids": []})
                found += 1
                if found >= max_fallback_dates:
                    break
            if found >= max_fallback_dates:
                break

    what = {
        'doc_type': _doc_type(doc_meta or {}),
        'mime': (doc_meta or {}).get('mime'),
        'filename': (doc_meta or {}).get('filename'),
        'labels': [],
    }

    who = {
        'people': sorted(people.values(), key=lambda x: (-x['count'], x.get('name') or '')),
        'orgs': sorted(orgs.values(), key=lambda x: (-x['count'], x.get('name') or '')),
    }

    things = [g for g in things_map.values() if (g.get('count') or 0) >= min_thing_count]
    things.sort(key=lambda x: (-(x.get('count') or 0), x.get('name') or ''))
    how = {'things': things}

    return {
        'doc_id': doc_id,
        'source_sha1': src_sha1,
        'who': who,
        'what': what,
        'when': whens,
        'where': wheres,
        'how': how,
        'stats': {
            'persons': len(who['people']),
            'orgs': len(who['orgs']),
            'dates': len(whens),
            'locations': len(wheres),
            'things': len(things),
            'mentions_total': len(mentions),
        },
    }


def process_dirs(
    er_or_coref_dir: str,
    out_dir: str,
    *,
    normalized_dir: Optional[str] = None,
    used_coref: bool = False,
    max_fallback_dates: int = 5,
    things_labels: Optional[set[str]] = None,
    min_thing_count: int = 1,
    allow_other_into_how: bool = False,
) -> Dict[str, Any]:
    """Processes directories of entities to build document properties.

    This function reads entities from the input directory, groups them by
    document, builds document properties for each document, and writes the
    results to the output directory. It also generates a run report with
    statistics.

    Args:
        er_or_coref_dir: The directory containing the entity files.
        out_dir: The directory to write the results to.
        normalized_dir: Optional directory containing normalized document
            metadata.
        used_coref: Whether the input directory contains coreference-resolved
            entities.
        max_fallback_dates: The maximum number of dates to extract from the
            text preview if no date mentions are found.
        things_labels: A set of labels to consider as "things" for the "how"
            category.
        min_thing_count: The minimum number of times a thing must be mentioned
            to be included in the "how" category.
        allow_other_into_how: Whether to include mentions with the "OTHER"
            label in the "how" category.

    Returns:
        A dictionary containing statistics about the run.
    """
    er_or_coref_dir = _resolve(er_or_coref_dir)
    out_dir = _resolve(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    meta_map = _load_doc_meta_map(normalized_dir)

    # Group mentions by doc base (filename)
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    unresolved_pronouns = 0
    for base, ent in _iter_entities_from_dir(er_or_coref_dir):
        grouped.setdefault(base, []).append(ent)
        if used_coref and ent.get('is_pronoun') and not ent.get('antecedent_mention_id'):
            unresolved_pronouns += 1

    docs = 0
    totals = Counter()
    top_people: Counter = Counter()
    top_orgs: Counter = Counter()

    for base, ents in grouped.items():
        # Build per-doc meta: prefer doc_meta by doc_id if available; else infer from base
        doc_id = (ents[0].get('doc_id') if ents else None)
        dm = meta_map.get(doc_id or '', {}) if doc_id else {}
        if not dm:
            dm = {'doc_id': doc_id, 'filename': base + '.json'}
        dp = build_doc_props(
            ents,
            doc_meta=dm,
            max_fallback_dates=max_fallback_dates,
            things_labels=things_labels,
            min_thing_count=min_thing_count,
            allow_other_into_how=allow_other_into_how,
        )
        out_path = os.path.join(out_dir, f"{base}.docprops.jsonl")
        with open(out_path, 'w', encoding='utf-8', newline='') as f:
            f.write(json.dumps(dp, ensure_ascii=False, sort_keys=True))
            f.write('\n')
        docs += 1
        totals['persons'] += dp['stats']['persons']
        totals['orgs'] += dp['stats']['orgs']
        totals['dates'] += dp['stats']['dates']
        totals['locations'] += dp['stats']['locations']
        for p in dp['who']['people']:
            top_people[p.get('name') or ''] += p.get('count') or 0
        for o in dp['who']['orgs']:
            top_orgs[o.get('name') or ''] += o.get('count') or 0
        totals['things'] += len(dp.get('how', {}).get('things', []))

    rep_dir = os.path.join(out_dir, '_reports')
    os.makedirs(rep_dir, exist_ok=True)
    with open(os.path.join(rep_dir, 'run_report.json'), 'w', encoding='utf-8') as f:
        json.dump({
            'docs': docs,
            'used_coref': bool(used_coref),
            'totals': dict(totals),
            'unresolved_pronouns': unresolved_pronouns,
            'top_people': [[n, c] for n, c in top_people.most_common(10) if n],
            'top_orgs': [[n, c] for n, c in top_orgs.most_common(10) if n],
        }, f, ensure_ascii=False, sort_keys=True, indent=2)
    return {'docs': docs, **dict(totals)}