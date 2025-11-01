from __future__ import annotations

import argparse
import json
import os
import re
from typing import Optional, Dict, Any

from .cli import _build_model  # reuse adapter construction
from .utils import select_gguf, _resolve


def main(argv: Optional[list[str]] = None) -> int:
    """The main entry point for the command-line interface.

    This function parses command-line arguments and runs a health check on the
    embedding adapters.

    Args:
        argv: A list of command-line arguments.

    Returns:
        An exit code.
    """
    p = argparse.ArgumentParser(prog='combo doctor', description='Health check for embedding adapters')
    p.add_argument('--adapter', choices=['local', 'llama-cpp', 'lc-llama-cpp'], default='local')
    p.add_argument('--llama-model-path', default=None, help='Path to GGUF model')
    p.add_argument('--models-dir', default=None, help='Directory to auto-select a GGUF if model path not provided')
    p.add_argument('--n-ctx', type=int, default=4096)
    p.add_argument('--n-threads', type=int, default=0)
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--dim', type=int, default=64)
    p.add_argument('--model', default='local-deterministic')
    p.add_argument('--json-out', default=None)
    args = p.parse_args(argv)

    # Auto-select model if using llama adapters and no explicit path
    model_path = args.llama_model_path
    if args.adapter in ('llama-cpp', 'lc-llama-cpp') and not model_path and args.models_dir:
        model_path = select_gguf(args.models_dir)
        if not model_path:
            print('No .gguf found in models directory')
            return 2
        args.llama_model_path = model_path

    rep: Dict[str, Any] = {
        'adapter': args.adapter,
        'model_path': model_path,
        'smoke_test': {'ok': False, 'error': None},
        'dim': None,
        'model_name': None,
    }
    # Optional binding versions for diagnostics
    try:
        import llama_cpp  # type: ignore
        rep['llama_cpp_version'] = getattr(llama_cpp, '__version__', None)
    except Exception:
        rep['llama_cpp_version'] = None
    try:
        import langchain_community  # type: ignore
        rep['langchain_community_version'] = getattr(langchain_community, '__version__', None)
    except Exception:
        rep['langchain_community_version'] = None
    try:
        model = _build_model(args)
        rep['dim'] = getattr(model, 'dim', None)
        rep['model_name'] = getattr(model, 'name', None)
        # Smoke embedding
        vecs = model.embed_texts(['hello world', 'quick test'], timeout_s=10.0)
        ok = isinstance(vecs, list) and len(vecs) == 2 and all(isinstance(v, list) and len(v) == model.dim for v in vecs)
        rep['smoke_test']['ok'] = bool(ok)
        if not ok:
            rep['smoke_test']['error'] = 'unexpected vector shapes'
            code = 2
        else:
            code = 0
    except SystemExit as e:
        rep['smoke_test']['error'] = str(e)
        code = 2
    except Exception as e:
        rep['smoke_test']['error'] = f'unexpected: {e}'
        code = 1

    if args.json_out:
        outp = _resolve(args.json_out)
        os.makedirs(os.path.dirname(outp) or '.', exist_ok=True)
        with open(outp, 'w', encoding='utf-8') as f:
            json.dump(rep, f, ensure_ascii=False, sort_keys=True, indent=2)
        print(f'Wrote doctor report: {outp}')
    else:
        print(json.dumps(rep, ensure_ascii=False, sort_keys=True, indent=2))
    return code
