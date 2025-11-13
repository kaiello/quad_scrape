from __future__ import annotations

import argparse
import json
import os
from typing import List, Dict, Any, Optional

from .adapters import REGISTRY
from .utils import select_gguf, _resolve as _resolve_path


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


def main(argv: Optional[List[str]] = None) -> int:
    """The main entry point for the command-line interface.

    This function parses command-line arguments and calls `embed_dir` to
    embed the documents.

    Args:
        argv: A list of command-line arguments.

    Returns:
        An exit code.
    """
    from .api import embed_dir, LocalDeterministicAdapter, EmbeddingModel
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
