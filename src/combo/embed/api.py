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


def _resolve(path: str) -> str:
    """Resolves a path to an absolute path.

    Args:
        path: The path to resolve.

    Returns:
        The absolute path.
    """
    return os.path.abspath(os.path.realpath(path))


def _load_normalized(path: str) -> Dict[str, Any]:
    """Loads a normalized JSON file.

    Args:
        path: The path to the file.

    Returns:
        The loaded JSON data.
    """
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_jsonl(path: str, rows: List[Dict[str, Any]]) -> int:
    """Writes a list of dictionaries to a JSONL file.

    Args:
        path: The path to the output file.
        rows: The list of dictionaries to write.

    Returns:
        The number of rows written.
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True))
            f.write("\n")
    return len(rows)


def _truncate_text_by_tokens(model: EmbeddingModel, text: str, max_tokens: Optional[int]) -> tuple[str, bool]:
    """Truncates text by a maximum number of tokens.

    Args:
        model: The embedding model to use for token counting.
        text: The text to truncate.
        max_tokens: The maximum number of tokens.

    Returns:
        A tuple of the truncated text and a boolean indicating whether the
        text was truncated.
    """
    if not max_tokens or max_tokens <= 0:
        return text, False
    tc = model.token_count(text)
    if tc is None:
        # Fallback to whitespace tokens
        toks = (text or "").split()
        if len(toks) <= max_tokens:
            return text, False
        return " ".join(toks[:max_tokens]), True
    if tc <= max_tokens:
        return text, False
    # Basic truncation by whitespace when no tokenizer access
    toks = (text or "").split()
    return (" ".join(toks[:max_tokens]), True) if len(toks) > max_tokens else (text, False)


def embed_dir(in_dir: str, out_dir: str, model: EmbeddingModel, batch: int = 64, timeout_s: float = 60.0) -> tuple[List[str], int]:
    """Embeds all normalized JSON files in a directory.

    Args:
        in_dir: The input directory.
        out_dir: The output directory.
        model: The embedding model to use.
        batch: The batch size for embedding.
        timeout_s: The timeout in seconds for embedding.

    Returns:
        A tuple of the list of written files and the total number of rows
        written.
    """
    in_dir = _resolve(in_dir)
    out_dir = _resolve(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    written: List[str] = []
    total_rows = 0
    skipped: List[str] = []
    errors: int = 0
    total_rows = 0
    for name in os.listdir(in_dir):
        if not name.lower().endswith(".json"):
            continue
        in_path = os.path.join(in_dir, name)
        base = os.path.splitext(name)[0]
        out_path = os.path.join(out_dir, f"{base}.embedded.jsonl")
        tmp_path = out_path + ".tmp"

        # Skip if final exists and is non-empty
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            skipped.append(out_path)
            continue

        data = _load_normalized(in_path)
        chunks = data.get("chunks", [])
        rows: List[Dict[str, Any]] = []
        texts: List[str] = []
        meta: List[Dict[str, Any]] = []
        for ch in chunks:
            t = ch.get("text", "")
            # token budget enforcement
            eff_max = None
            if getattr(model, 'max_tokens', None):
                eff_max = model.max_tokens
            # allow CLI override via args.max_model_tokens handled in _build_model
            # we keep model.max_tokens which may have been set in adapter
            trunc_t, truncated = _truncate_text_by_tokens(model, t, eff_max)
            texts.append(trunc_t)
            meta.append({
                "doc_id": data.get("doc", {}).get("doc_id"),
                "chunk_id": ch.get("chunk_id"),
                "truncated": truncated,
            })
        try:
            # batch
            i = 0
            while i < len(texts):
                batch_texts = texts[i:i+batch]
                vecs = model.embed_texts(batch_texts, timeout_s=timeout_s)
                import hashlib
                for j, vec in enumerate(vecs):
                    rows.append({
                        **meta[i+j],
                        "model": model.name,
                        "dim": model.dim,
                        "text_sha1": hashlib.sha1((texts[i+j] or "").encode("utf-8")).hexdigest(),
                        "embedding": vec,
                    })
                i += batch

            # write to tmp then atomically replace
            os.makedirs(os.path.dirname(tmp_path) or '.', exist_ok=True)
            count = _write_jsonl(tmp_path, rows)
            os.replace(tmp_path, out_path)
            total_rows += count
            written.append(out_path)
        except Exception:
            errors += 1
            # cleanup tmp on error
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
    return written, total_rows
