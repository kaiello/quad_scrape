from __future__ import annotations

import json
import os
from typing import Dict, Optional


def load_cache(path: Optional[str] = None) -> Dict[str, str]:
    """Loads a UEI cache from a JSON file.

    Args:
        path: The path to the JSON file.

    Returns:
        A dictionary mapping normalized names to UEI IDs.
    """
    if not path or not os.path.isfile(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    out: Dict[str, str] = {}
    for k, v in (data or {}).items():
        key = str(k).strip().lower()
        if "|" in key:
            key = key.split("|", 1)[1]
        if isinstance(v, list):
            for item in v:
                sid = str((item or {}).get("id") or "").strip()
                if sid:
                    out[key] = sid
                    break
        else:
            out[key] = str(v)
    return out


def lookup(normalized_name: str, cache: Dict[str, str]) -> Optional[str]:
    """Looks up a UEI ID for a normalized name.

    Args:
        normalized_name: The normalized name to look up.
        cache: The UEI cache.

    Returns:
        The UEI ID, or None if not found.
    """
    return cache.get((normalized_name or '').strip().lower())
