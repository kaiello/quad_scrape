from __future__ import annotations

# Minimal stub to allow import in optional integration test.

from typing import Optional


def load(facts_dir: str, uri: str, user: str, password: str, *, batch: Optional[int] = 1000) -> None:
    # Intentionally a no-op placeholder; real loader can be implemented in Step F.
    return None

