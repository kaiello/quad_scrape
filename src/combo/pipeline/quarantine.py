from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional

JSON = Dict[str, Any]


def _read_jsonl(path: str) -> Iterable[JSON]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            yield json.loads(ln)


def _short(s: str, n: int = 64) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def summarize_quarantine(quarantine_dir: str, out_md: str, out_json: Optional[str] = None) -> str:
    q_ent = os.path.join(quarantine_dir, "entities.jsonl")
    q_rel = os.path.join(quarantine_dir, "relations.jsonl")

    ent_rows = list(_read_jsonl(q_ent))
    rel_rows = list(_read_jsonl(q_rel))

    # Counters
    reasons: Counter[str] = Counter()
    pred_counts: Counter[str] = Counter()
    reason_to_examples: Dict[str, List[str]] = defaultdict(list)
    missing_keys_counts: Counter[str] = Counter()

    # Entities
    for r in ent_rows:
        rs = r.get("reasons", []) or []
        for reason in rs:
            reasons[reason] += 1
            key = r.get("canonical_id", "unknown")
            if len(reason_to_examples[reason]) < 5:
                reason_to_examples[reason].append(_short(f"entity:{key}"))
        # extract missing_keys:<k1,k2> if present
        for reason in rs:
            if isinstance(reason, str) and reason.startswith("missing_keys:"):
                for k in reason.split(":", 1)[1].split(","):
                    k = (k or "").strip()
                    if k:
                        missing_keys_counts[k] += 1

    # Relations
    for r in rel_rows:
        rs = r.get("reasons", []) or []
        gk = r.get("group_key", ["?", "?", "?"])
        pred = gk[1] if len(gk) >= 2 else r.get("predicate", "?")
        pred_counts[pred] += 1
        for reason in rs:
            reasons[reason] += 1
            if len(reason_to_examples[reason]) < 5:
                example = "rel:" + "|".join(str(x) for x in gk)
                reason_to_examples[reason].append(_short(example))

    total_ent = len(ent_rows)
    total_rel = len(rel_rows)
    total = total_ent + total_rel

    # Build Markdown
    lines: List[str] = []
    lines.append("# Quarantine Summary\n")
    lines.append(f"- Total quarantined: **{total}** (entities={total_ent}, relations={total_rel})\n")

    # Reasons
    lines.append("## Top Reasons\n")
    if reasons:
        for reason, cnt in reasons.most_common():
            ex = ", ".join(reason_to_examples.get(reason, []))
            lines.append(f"- **{reason}** — {cnt}  \n  examples: {ex}\n")
    else:
        lines.append("- *(none)*\n")

    # Predicates affected
    lines.append("\n## Relations by Predicate\n")
    if pred_counts:
        for p, c in pred_counts.most_common():
            lines.append(f"- `{p}` — {c}")
    else:
        lines.append("- *(none)*")

    # Missing keys
    lines.append("\n## Missing Merge Keys (Entities)\n")
    if missing_keys_counts:
        for k, c in missing_keys_counts.most_common():
            lines.append(f"- `{k}` — {c}")
    else:
        lines.append("- *(none)*")

    os.makedirs(os.path.dirname(out_md) or ".", exist_ok=True)
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    if out_json:
        summary = {
            "totals": {"all": total, "entities": total_ent, "relations": total_rel},
            "reasons": reasons.most_common(),
            "predicates": pred_counts.most_common(),
            "missing_keys": missing_keys_counts.most_common(),
            "examples": {k: v for k, v in reason_to_examples.items()},
        }
        with open(out_json, "w", encoding="utf-8") as fj:
            json.dump(summary, fj, ensure_ascii=False, indent=2, sort_keys=True)

    return out_md


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="combo quarantine summarize", description="Summarize promotion quarantine outputs")
    ap.add_argument("quarantine_dir", help="Directory containing entities.jsonl and relations.jsonl")
    ap.add_argument("--out", required=True, help="Output Markdown path (e.g., facts/_reports/quarantine_summary.md)")
    ap.add_argument("--json", default=None, help="Optional JSON summary path")
    args = ap.parse_args(argv)
    try:
        summarize_quarantine(args.quarantine_dir, args.out, args.json)
        return 0
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

