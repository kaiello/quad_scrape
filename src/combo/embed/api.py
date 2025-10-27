from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional
import hashlib
import random


class EmbeddingModel(ABC):
    name: str
    dim: int
    max_tokens: Optional[int]

    @abstractmethod
    def embed_texts(self, texts: List[str], timeout_s: float) -> List[List[float]]:  # pragma: no cover - interface
        ...

    def token_count(self, text: str) -> Optional[int]:  # pragma: no cover - optional
        return None


@dataclass
class LocalDeterministicAdapter(EmbeddingModel):
    dim: int = 64
    name: str = "local-deterministic"
    max_tokens: Optional[int] = None

    def _vec_for_text(self, text: str) -> List[float]:
        # Deterministic pseudo-random vector based on SHA1(text|name|dim)
        h = hashlib.sha1((self.name + "|" + str(self.dim) + "|" + text).encode("utf-8")).hexdigest()
        seed = int(h[:16], 16)
        rng = random.Random(seed)
        return [rng.uniform(-1.0, 1.0) for _ in range(self.dim)]

    def embed_texts(self, texts: List[str], timeout_s: float) -> List[List[float]]:
        return [self._vec_for_text(t or "") for t in texts]

    def token_count(self, text: str) -> Optional[int]:
        return len((text or "").split())

