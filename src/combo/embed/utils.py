from __future__ import annotations

import os
import re
from typing import Optional


def _resolve(path: str) -> str:
    """Resolves a path to an absolute path.

    Args:
        path: The path to resolve.

    Returns:
        The absolute path.
    """
    return os.path.abspath(os.path.realpath(path))


def select_gguf(models_dir: str) -> Optional[str]:
    """Selects a GGUF model from a directory.

    This function searches for GGUF files in the specified directory,
    preferring models with "bge", "nomic", or "embed" in their names. It
    returns the smallest of the preferred models, or the smallest of all GGUF
    files if no preferred models are found.

    Args:
        models_dir: The directory to search for models.

    Returns:
        The path to the selected model, or None if no GGUF files are found.
    """
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

