from __future__ import annotations

import os
import re
from typing import Optional


def _resolve(path: str) -> str:
    return os.path.abspath(os.path.realpath(path))


def select_gguf(models_dir: str) -> Optional[str]:
    models_dir = _resolve(models_dir)
    if not os.path.isdir(models_dir):
        return None
    ggufs = [os.path.join(models_dir, n) for n in os.listdir(models_dir) if n.lower().endswith('.gguf')]
    if not ggufs:
        return None
    prefer = [p for p in ggufs if re.search(r"\b(bge|nomic|embed)\b", os.path.basename(p), flags=re.I)]
    cand = prefer or ggufs
    cand.sort(key=lambda p: os.path.getsize(p))
    return cand[0]

