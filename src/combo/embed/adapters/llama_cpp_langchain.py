from __future__ import annotations

from typing import List, Optional

from ..api import EmbeddingModel


class LlamaCppLCAdapter(EmbeddingModel):
    def __init__(
        self,
        model_path: str,
        dim: Optional[int] = None,
        n_ctx: int = 4096,
        max_tokens: Optional[int] = None,
        **_: object,
    ):
        try:
            from langchain_community.embeddings import LlamaCppEmbeddings  # type: ignore
        except Exception as e:  # pragma: no cover - optional dep
            raise RuntimeError("langchain-community is not installed") from e

        self._emb = LlamaCppEmbeddings(model_path=model_path, n_ctx=n_ctx)
        self.name = f"lc-llama.cpp:{model_path.split('/')[-1]}"
        self.dim = dim or len(self._emb.embed_query(""))
        self.max_tokens = max_tokens or n_ctx

    def embed_texts(self, texts: List[str], timeout_s: float) -> List[List[float]]:
        vecs = self._emb.embed_documents(texts)
        return [list(map(float, v)) for v in vecs]

    def token_count(self, text: str) -> Optional[int]:
        return None

