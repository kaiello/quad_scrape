from __future__ import annotations

from typing import List, Optional

from ..api import EmbeddingModel


class LlamaCppLCAdapter(EmbeddingModel):
    """An embedding model adapter for `llama-cpp-python` via `langchain`.

    This class provides an interface to `llama-cpp-python` for generating
    embeddings using the `langchain` library.

    Attributes:
        name: The name of the model.
        dim: The dimension of the embeddings.
        max_tokens: The maximum number of tokens the model can handle.
    """
    def __init__(
        self,
        model_path: str,
        dim: Optional[int] = None,
        n_ctx: int = 4096,
        max_tokens: Optional[int] = None,
        **_: object,
    ):
        """Initializes the LlamaCppLCAdapter.

        Args:
            model_path: The path to the GGUF model file.
            dim: The dimension of the embeddings. If None, it will be inferred
                from the model.
            n_ctx: The context size.
            max_tokens: The maximum number of tokens the model can handle.
        """
        try:
            from langchain_community.embeddings import LlamaCppEmbeddings  # type: ignore
        except Exception as e:  # pragma: no cover - optional dep
            raise RuntimeError("langchain-community is not installed") from e

        self._emb = LlamaCppEmbeddings(model_path=model_path, n_ctx=n_ctx)
        self.name = f"lc-llama.cpp:{model_path.split('/')[-1]}"
        self.dim = dim or len(self._emb.embed_query(""))
        self.max_tokens = max_tokens or n_ctx

    def embed_texts(self, texts: List[str], timeout_s: float) -> List[List[float]]:
        """Embeds a list of texts.

        Args:
            texts: A list of texts to embed.
            timeout_s: The timeout in seconds (unused).

        Returns:
            A list of embeddings.
        """
        vecs = self._emb.embed_documents(texts)
        return [list(map(float, v)) for v in vecs]

    def token_count(self, text: str) -> Optional[int]:
        """Counts the number of tokens in a text.

        Args:
            text: The text to count tokens for.

        Returns:
            None, as this is not implemented.
        """
        return None

