from __future__ import annotations

from .llama_cpp import LlamaCppAdapter  # type: ignore
from .llama_cpp_langchain import LlamaCppLCAdapter  # type: ignore


REGISTRY = {
    "local": "LOCAL",  # sentinel; resolved elsewhere
    "llama-cpp": LlamaCppAdapter,
    "lc-llama-cpp": LlamaCppLCAdapter,
}

