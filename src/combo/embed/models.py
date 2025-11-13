from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional


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
