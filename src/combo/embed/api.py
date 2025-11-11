from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional
import hashlib
import random


class EmbeddingModel(ABC):
    """An abstract base class for embedding models.

    Attributes:
        name: The name of the model.
        dim: The dimension of the embeddings.
        max_tokens: The maximum number of tokens the model can handle.
    """
    name: str
    dim: int
    max_tokens: Optional[int]

    @abstractmethod
    def embed_texts(self, texts: List[str], timeout_s: float) -> List[List[float]]:  # pragma: no cover - interface
        """Embeds a list of texts.

        Args:
            texts: A list of texts to embed.
            timeout_s: The timeout in seconds.

        Returns:
            A list of embeddings.
        """
        ...

    def token_count(self, text: str) -> Optional[int]:  # pragma: no cover - optional
        """Counts the number of tokens in a text.

        Args:
            text: The text to count tokens for.

        Returns:
            The number of tokens, or None if not implemented.
        """
        return None


@dataclass
class LocalDeterministicAdapter(EmbeddingModel):
    """A local, deterministic embedding model for testing.

    This model generates a pseudo-random vector for each text based on a hash
    of the text, the model name, and the dimension.

    Attributes:
        dim: The dimension of the embeddings.
        name: The name of the model.
        max_tokens: The maximum number of tokens the model can handle.
    """
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
        """Embeds a list of texts.

        Args:
            texts: A list of texts to embed.
            timeout_s: The timeout in seconds (unused).

        Returns:
            A list of embeddings.
        """
        return [self._vec_for_text(t or "") for t in texts]

    def token_count(self, text: str) -> Optional[int]:
        """Counts the number of tokens in a text.

        Args:
            text: The text to count tokens for.

        Returns:
            The number of tokens.
        """
        return len((text or "").split())

