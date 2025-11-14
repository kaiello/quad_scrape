from __future__ import annotations

# ruff: noqa

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

JSON = Dict[str, Any]


def _read_jsonl(p: str) -> Iterable[JSON]:
    if not os.path.exists(p):
        return []
    with open(p, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                yield json.loads(ln)


def _load_schema(path: str) -> JSON:
    txt = open(path, "r", encoding="utf-8").read()
    if yaml is not None:
        return yaml.safe_load(txt)  # type: ignore
    return json.loads(txt)


def _labels_satisfy(labels: List[str], allowed: List[str]) -> bool:
    return ("*" in allowed) or any(l in allowed for l in labels)


def _markdown_report(report: JSON) -> str:
    def _section(title: str) -> str:
        return f"\n## {title}\n"
    lines: List[str] = []
    lines.append("# Doctor Preflight Report\n")
    lines.append(f"- Schema version: **{report.get('schema_version','?')}**")
    lines.append(f"- Thresholds: `conf_thr={report.get('conf_thr')}`, `min_ev={report.get('min_ev')}`\n")
    c = report.get("counts", {})
    lines.append("### Counts\n")
    lines.append(f"- Canonical entities indexed: **{c.get('canon_entities',0)}**")
    lines.append(f"- Relation groups: **{c.get('relation_groups',0)}**\n")

    def _list_pairs(title: str, pairs):
        lines.append(_section(title))
        if pairs:
            for k, v in pairs:
                lines.append(f"- `{k}` — {v}")
        else:
            lines.append("- *(none)*")

    _list_pairs("Unknown predicates", report.get("unknown_predicates", []))
    _list_pairs("Unknown entity types", report.get("unknown_entity_types", []))
    _list_pairs("Domain/Range mismatches (by predicate)", report.get("domain_range_mismatches", []))
    _list_pairs("Missing merge keys (type:key)", report.get("missing_keys", []))

    lines.append(_section("TRL out-of-range"))
    lines.append(f"- Count: **{report.get('trl_out_of_range',0)}**")

    lines.append(_section("Below-threshold relation groups (preview)"))
    lines.append(f"- Count: **{report.get('below_threshold_groups',0)}**")

    return "\n".join(lines) + "\n"


def run_doctor(
    mentions_entities_path: str,
    mentions_relations_path: str,
    linked_entities_path: str,
    schema_path: str,
    conf_thr: float,
    min_ev: int,
    out_dir: Optional[str] = None,
    md_out: Optional[str] = None,
) -> Tuple[str, int]:
    sch = _load_schema(schema_path)
    entities = sch.get("entities", {})
    rels = sch.get("relations", {})
    schema_version = sch.get("schema_version", "0.0.0")

    # index canon
    canon: Dict[str, JSON] = {}
    for row in _read_jsonl(linked_entities_path):
        cid = row.get("canonical_id")
        if cid:
            canon[cid] = row

    def _entity_rule(etype: str) -> Optional[JSON]:
        return entities.get(etype)

    def _predicate_rule(p: str) -> Optional[JSON]:
        return rels.get(p)

    # counters
    unknown_pred: Counter[str] = Counter()
    unknown_type: Counter[str] = Counter()
    missing_keys: Counter[str] = Counter()
    trl_out = 0
    domain_range_bad: Counter[str] = Counter()
    below_threshold_groups = 0

    # entity mention type sanity
    for m in _read_jsonl(mentions_entities_path):
        et = m.get("type", "?")
        if et not in entities:
            unknown_type[et] += 1
        # if canonical is TRL, check value range (if available)
        cid = m.get("canonical_id")
        if cid in canon:
            c = canon[cid]
            rule = _entity_rule(c.get("type", ""))
            cons = (rule or {}).get("constraints") or {}
            if "value_range" in cons and ("TRL" in set(c.get("labels", [])) or (c.get("type") or "").endswith("TRL"))):
                try:
                    v = float((c.get("key") or {}).get("value"))
                except Exception:
                    trl_out += 1
                else:
                    lo, hi = cons["value_range"]
                    if not (float(lo) <= v <= float(hi)):
                        trl_out += 1

    # relation grouping and stats
    groups: Dict[Tuple[str, str, str], List[JSON]] = defaultdict(list)
    for r in _read_jsonl(mentions_relations_path):
        groups[(r.get("subj_canonical_id"), r.get("predicate"), r.get("obj_canonical_id"))].append(r)

    for (subj, pred, obj), ms in groups.items():
        # predicate allow-list
        pr = _predicate_rule(str(pred))
        if not pr:
            unknown_pred[str(pred)] += 1
            continue
        s = canon.get(subj)
        o = canon.get(obj)
        if not s or not o:
            # skip domain-range if we can't resolve either
            continue
        # domain/range
        if not (
            _labels_satisfy(s.get("labels", []), pr.get("domain", ["*"]))
            and _labels_satisfy(o.get("labels", []), pr.get("range", ["*"]))
        ):
            domain_range_bad[str(pred)] += 1
            continue
        # keys present (merge keys)
        for c in (s, o):
            rule = _entity_rule(c.get("type", "")) or {}
            keys = rule.get("key", [])
            for k in keys:
                if not (c.get("key") or {}).get(k):
                    missing_keys[f"{c.get('type')}:{k}"] += 1
        # threshold preview
        confs = [float(m.get("confidence", 0.0)) for m in ms]
        sents = {m.get("sent_id") for m in ms if m.get("sent_id")}
        avg = sum(confs) / len(confs) if confs else 0.0
        if not (avg >= float(conf_thr) and len(sents) >= int(min_ev)):
            below_threshold_groups += 1

    report = {
        "schema_version": schema_version,
        "conf_thr": float(conf_thr),
        "min_ev": int(min_ev),
        "counts": {"canon_entities": len(canon), "relation_groups": len(groups)},
        "unknown_predicates": unknown_pred.most_common(),
        "unknown_entity_types": unknown_type.most_common(),
        "domain_range_mismatches": domain_range_bad.most_common(),
        "missing_keys": missing_keys.most_common(),
        "trl_out_of_range": trl_out,
        "below_threshold_groups": below_threshold_groups,
    }

    out_path = ""
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "doctor_report.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, sort_keys=True)

    if md_out:
        md = _markdown_report(report)
        os.makedirs(os.path.dirname(md_out) or ".", exist_ok=True)
        with open(md_out, "w", encoding="utf-8") as f:
            f.write(md)

    # exit code policy: non-zero if any hard blockers
    hard = (
        sum(c for _, c in unknown_pred.items())
        + sum(c for _, c in unknown_type.items())
        + int(trl_out)
        + sum(c for _, c in domain_range_bad.items())
    )
    exit_code = 1 if hard > 0 else 0
    return (out_path or "<stdout>", exit_code)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="combo promote --doctor", description="Preflight checks for promotion")
    ap.add_argument("mentions_entities")
    ap.add_argument("mentions_relations")
    ap.add_argument("linked_entities")
    ap.add_argument("--schema", required=True)
    ap.add_argument("--conf", type=float, default=0.7)
    ap.add_argument("--min-evidence", type=int, default=2)
    ap.add_argument("--out", default=None, help="Directory to write doctor_report.json")
    ap.add_argument("--md-out", default=None, help="Optional Markdown path (e.g., facts/_reports/doctor_report.md)")
    args = ap.parse_args(argv)
    path, code = run_doctor(
        args.mentions_entities,
        args.mentions_relations,
        args.linked_entities,
        args.schema,
        args.conf,
        args.min_evidence,
        args.out,
        args.md_out,
    )
    if path != "<stdout>":
        print(f"[doctor] wrote {path}")
    if args.md_out:
        print(f"[doctor] wrote {args.md_out}")
    return int(code)


