from __future__ import annotations

from typing import List, Optional

from ..api import EmbeddingModel


class LlamaCppAdapter(EmbeddingModel):
    """An embedding model adapter for `llama-cpp-python`.

    This class provides an interface to `llama-cpp-python` for generating
    embeddings.

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
        n_threads: Optional[int] = None,
        seed: int = 0,
        max_tokens: Optional[int] = None,
    ):
        """Initializes the LlamaCppAdapter.

        Args:
            model_path: The path to the GGUF model file.
            dim: The dimension of the embeddings. If None, it will be inferred
                from the model.
            n_ctx: The context size.
            n_threads: The number of threads to use.
            seed: The random seed.
            max_tokens: The maximum number of tokens the model can handle.
        """
        try:
            from llama_cpp import Llama  # type: ignore
        except Exception as e:  # pragma: no cover - optional dep
            raise RuntimeError("llama-cpp-python is not installed") from e

        self.name = f"llama.cpp:{model_path.split('/')[-1]}"
        self._llm = Llama(
            model_path=model_path,
            embedding=True,
            n_ctx=n_ctx,
            n_threads=n_threads or 0,
            seed=seed,
            verbose=False,
        )
        self.dim = dim or self._infer_dim()
        self.max_tokens = max_tokens or n_ctx

    def _infer_dim(self) -> int:
        # llama-cpp expects positional or keyword 'input'
        try:
            out = self._llm.create_embedding("", pooling_type=2)
        except TypeError:
            out = self._llm.create_embedding("")
        emb = out["data"][0]["embedding"]
        return len(emb)

    def embed_texts(self, texts: List[str], timeout_s: float) -> List[List[float]]:
        """Embeds a list of texts.

        Args:
            texts: A list of texts to embed.
            timeout_s: The timeout in seconds (unused).

        Returns:
            A list of embeddings.
        """
        # Use positional arg for compatibility across versions
        try:
            out = self._llm.create_embedding(texts, pooling_type=2)
        except TypeError:
            out = self._llm.create_embedding(texts)
        data = sorted(out["data"], key=lambda d: d["index"])  # ensure order
        vecs = [list(map(float, d["embedding"])) for d in data]
        if any(len(v) != self.dim for v in vecs):
            raise RuntimeError(f"Unexpected embedding dim (expected {self.dim}).")
        return vecs

    def token_count(self, text: str) -> Optional[int]:
        """Counts the number of tokens in a text.

        Args:
            text: The text to count tokens for.

        Returns:
            The number of tokens.
        """
        toks = self._llm.tokenize(text.encode("utf-8"), add_bos=False)
        return len(toks)
