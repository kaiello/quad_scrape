from __future__ import annotations

import json
import os
from typing import Dict, Optional


def load_cache(path: Optional[str] = None) -> Dict[str, str]:
    if not path or not os.path.isfile(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    out: Dict[str, str] = {}
    for k, v in (data or {}).items():
        # Key may be plain normalized name or include a prefix like "organization|name"
        key = str(k).strip().lower()
        if "|" in key:
            key = key.split("|", 1)[1]
        if isinstance(v, list):
            # take first id present
            for item in v:
                sid = str((item or {}).get("id") or "").strip()
                if sid:
                    out[key] = sid
                    break
        else:
            out[key] = str(v)
    return out


def lookup(normalized_name: str, cache: Dict[str, str]) -> Optional[str]:
    return cache.get((normalized_name or '').strip().lower())
