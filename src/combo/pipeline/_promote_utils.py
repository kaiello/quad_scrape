from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


def labels_satisfy(role_labels: Sequence[str], allowed_labels: Sequence[str]) -> bool:
    if not allowed_labels:
        return False
    if len(allowed_labels) == 1 and allowed_labels[0] == "*":
        return True
    role_set = {str(x) for x in role_labels}
    allow_set = {str(x) for x in allowed_labels}
    return bool(role_set & allow_set)


def entity_keys_present(canon: Mapping[str, Any], schema_entities: Mapping[str, Any]) -> bool:
    etype = canon.get("type")
    if not etype or etype not in schema_entities:
        return False
    req = schema_entities[etype].get("required", [])
    key_fields = schema_entities[etype].get("key", [])
    key = canon.get("key") or {}
    # Required props present
    for f in req:
        if f not in key and f not in (canon.get("props") or {}):
            return False
    # Merge key fields present
    for f in key_fields:
        if f not in key:
            return False
    return True


def type_constraints_ok(canon: Mapping[str, Any], schema_entities: Mapping[str, Any]) -> bool:
    etype = canon.get("type")
    if not etype or etype not in schema_entities:
        return False
    cons = schema_entities[etype].get("constraints") or {}
    if "value_range" in cons:
        vr = cons["value_range"]
        try:
            v = (canon.get("key") or {}).get("value")
            if v is None:
                return False
            return vr[0] <= float(v) <= vr[1]
        except Exception:
            return False
    return True


def missing_merge_keys(canon: Mapping[str, Any], schema_entities: Mapping[str, Any]) -> List[str]:
    """Return list of missing merge key field names for the entity type.

    Only considers the entity's schema `key` fields (merge keys). Does not include
    general required fields, to keep the reason focused on merge identity.
    """
    etype = canon.get("type")
    if not etype or etype not in schema_entities:
        return []
    key_fields = schema_entities[etype].get("key", [])
    key = canon.get("key") or {}
    missing: List[str] = []
    for f in key_fields:
        if f not in key or key.get(f) in (None, ""):
            missing.append(str(f))
    return missing


def domain_range_ok(
    subj_labels: Sequence[str],
    obj_labels: Sequence[str],
    predicate_rule: Mapping[str, Any],
) -> bool:
    dom = predicate_rule.get("domain") or ["*"]
    ran = predicate_rule.get("range") or ["*"]
    return labels_satisfy(subj_labels, dom) and labels_satisfy(obj_labels, ran)


def predicate_specific_ok(
    predicate: str,
    subj: Mapping[str, Any],
    obj: Mapping[str, Any],
    rel_props: Optional[Mapping[str, Any]],
    schema_entities: Mapping[str, Any],
) -> bool:
    # TRL constraints: ensure obj type constraints are satisfied if kb_TRL
    if predicate in {"STARTS_AT_TRL", "ENDS_AT_TRL", "AT_TRL"}:
        if (obj.get("type") or "").endswith("TRL") or "TRL" in (obj.get("labels") or []):
            return type_constraints_ok(obj, schema_entities)
    return True


def stable_json_sort_key(obj: Mapping[str, Any]) -> str:
    # Late import to avoid heavy dependency; json is stdlib
    import json

    return json.dumps(obj, ensure_ascii=False, sort_keys=True)
