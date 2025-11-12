from __future__ import annotations

import argparse
from typing import Optional, List

from .api import link_entities


def main(argv: Optional[List[str]] = None) -> int:
    """The main entry point for the command-line interface.

    This function parses command-line arguments and calls `link_entities` to
    link entities across documents.

    Args:
        argv: A list of command-line arguments.

    Returns:
        An exit code.
    """
    ap = argparse.ArgumentParser(prog='combo link', description='Cross-doc entity linking with SQLite registry and offline adapters')
    ap.add_argument('input_dir', help='Directory with *.entities.jsonl (coref-augmented preferred)')
    ap.add_argument('--registry', required=True, help='Path to SQLite registry file')
    ap.add_argument('--out', required=True, help='Output directory for linked results')
    ap.add_argument('--link-conf', type=float, default=0.75)
    ap.add_argument('--enable-fts', action='store_true')
    ap.add_argument('--materialize-blocking', action='store_true')
    ap.add_argument('--adapters', default='', help='CSV adapters: wikidata,uei')
    ap.add_argument('--wikidata-cache', default=None)
    ap.add_argument('--uei-cache', default=None)
    args = ap.parse_args(argv)
    try:
        adapters = [s.strip() for s in args.adapters.split(',') if s.strip()]
        adapter_paths = {'wikidata': args.wikidata_cache, 'uei': args.uei_cache}
        link_entities(
            args.input_dir,
            args.out,
            args.registry,
            link_conf=args.link_conf,
            enable_fts=args.enable_fts,
            materialize_blocking=args.materialize_blocking,
            adapters=adapters,
            adapter_paths=adapter_paths,
        )
        return 0
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1
