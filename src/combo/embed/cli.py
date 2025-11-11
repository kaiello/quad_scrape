from __future__ import annotations

import argparse
import json
import os
from typing import List, Dict, Any, Optional

from .api import LocalDeterministicAdapter, EmbeddingModel
from .adapters import REGISTRY
from .utils import select_gguf, _resolve as _resolve_path


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


def _build_model(args: argparse.Namespace) -> EmbeddingModel:
    """Builds an embedding model from command-line arguments.

    Args:
        args: The command-line arguments.

    Returns:
        The embedding model.
    """
    max_tokens = None
    if getattr(args, "max_model_tokens", None):
        max_tokens = args.max_model_tokens if args.max_model_tokens > 0 else None

    if args.adapter == "local":
        dim = args.dim if args.dim and args.dim > 0 else 64
        return LocalDeterministicAdapter(dim=dim, name=args.model, max_tokens=max_tokens)

    if args.adapter in ("llama-cpp", "lc-llama-cpp"):
        # Prefer explicit path; otherwise try models-dir auto-pick
        if not args.llama_model_path and getattr(args, "models_dir", None):
            picked = select_gguf(args.models_dir)
            if not picked:
                raise SystemExit("No .gguf found in --models-dir")
            args.llama_model_path = picked
        if not args.llama_model_path:
            raise SystemExit("--llama-model-path is required for llama.cpp adapters (or provide --models-dir)")
        Adapter = REGISTRY[args.adapter]
        if Adapter == "LOCAL":  # pragma: no cover - defensive
            raise SystemExit("internal error: LOCAL sentinel in registry")
        try:
            return Adapter(
                model_path=args.llama_model_path,
                dim=(args.dim if args.dim and args.dim > 0 else None),
                n_ctx=args.n_ctx,
                n_threads=(args.n_threads or None),
                seed=args.seed,
                max_tokens=max_tokens,
            )
        except Exception as e:  # graceful fallback for CI/Windows issues
            import sys
            print(f"[warn] llama.cpp init failed ({e}); falling back to local adapter", file=sys.stderr)
            return LocalDeterministicAdapter(dim=(args.dim if args.dim and args.dim > 0 else 64), name="local-fallback", max_tokens=max_tokens)

    raise SystemExit(f"Unknown adapter: {args.adapter}")


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


def main(argv: Optional[List[str]] = None) -> int:
    """The main entry point for the command-line interface.

    This function parses command-line arguments and calls `embed_dir` to
    embed the documents.

    Args:
        argv: A list of command-line arguments.

    Returns:
        An exit code.
    """
    p = argparse.ArgumentParser(prog="combo embed", description="Embed normalized chunks to vectors")
    p.add_argument("normalized_dir", help="Directory of normalized JSON files")
    p.add_argument("--out", required=True, help="Output directory for embeddings (JSONL)")
    p.add_argument("--adapter", choices=["local", "llama-cpp", "lc-llama-cpp"], default="local")
    p.add_argument("--model", default="local-deterministic")
    p.add_argument("--dim", type=int, default=64)
    p.add_argument("--batch", type=int, default=64)
    p.add_argument("--llama-model-path", default=None)
    p.add_argument("--models-dir", default=None)
    p.add_argument("--n-ctx", type=int, default=4096)
    p.add_argument("--n-threads", type=int, default=0)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--max-model-tokens", type=int, default=0)
    p.add_argument("--timeout", type=float, default=60.0)
    p.add_argument("--force-local", action="store_true", help="Force local deterministic adapter, bypassing llama.cpp")
    args = p.parse_args(argv)

    try:
        if args.force_local:
            import sys
            print("[warn] forcing local adapter", file=sys.stderr)
            model = LocalDeterministicAdapter(dim=(args.dim if args.dim and args.dim > 0 else 64), name=args.model)
        else:
            model = _build_model(args)
        used_local_fallback = getattr(model, 'name', '') == 'local-fallback'
        outs, total_rows = embed_dir(args.normalized_dir, args.out, model, batch=args.batch, timeout_s=args.timeout)
        # manifest and run report
        manifest = {
            "adapter": args.adapter,
            "model": getattr(model, 'name', None),
            "dim": getattr(model, 'dim', None),
            "files": sorted([os.path.basename(p) for p in outs]),
            "count_files": len(outs),
            "count_rows": total_rows,
        }
        man_path = os.path.join(_resolve_path(args.out), 'manifest.json')
        with open(man_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, sort_keys=True, indent=2)
        # simple run report
        rep_dir = os.path.join(_resolve_path(args.out), '_reports')
        os.makedirs(rep_dir, exist_ok=True)
        rep_path = os.path.join(rep_dir, 'run_report.json')
        notes = []
        if used_local_fallback:
            notes = ["llama_cpp_decode_error", "fallback_to_local"]
        if args.force_local:
            notes.append("force_local")
        with open(rep_path, 'w', encoding='utf-8') as f:
            json.dump({"errors": 0, "written": len(outs), "notes": notes}, f, ensure_ascii=False, sort_keys=True, indent=2)
        print(f"Wrote {len(outs)} embedded file(s) to {os.path.abspath(args.out)}")
        return 0
    except SystemExit as e:
        # Argument/adapter errors use code 2
        msg = str(e)
        if msg:
            print(msg)
        return 2
    except Exception as e:  # unexpected
        print(f"Unexpected error: {e}")
        return 1
