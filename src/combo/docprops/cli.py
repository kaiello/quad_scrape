from __future__ import annotations

import argparse
from typing import Optional, List

from .api import process_dirs


def main(argv: Optional[List[str]] = None) -> int:
    """The main entry point for the command-line interface.

    This function parses command-line arguments and calls `process_dirs` to
    build document properties.

    Args:
        argv: A list of command-line arguments.

    Returns:
        An exit code.
    """
    ap = argparse.ArgumentParser(prog='combo docprops', description='Aggregate Who/What/When/Where/How from ER/Coref entities')
    ap.add_argument('input_dir', help='ER or Coref directory (expects *.entities.jsonl)')
    ap.add_argument('--out', required=True, help='Output directory for 4W results')
    ap.add_argument('--coref-dir', default=None, help='If provided, prefer entities from this coref directory')
    ap.add_argument('--normalized-dir', default=None, help='Optional normalized dir for doc metadata')
    ap.add_argument('--max-fallback-dates', type=int, default=5)
    ap.add_argument('--things-labels', default=None, help='CSV labels to include as HOW things (default: built-in set)')
    ap.add_argument('--min-thing-count', type=int, default=1)
    ap.add_argument('--allow-other-into-how', action='store_true')
    args = ap.parse_args(argv)
    try:
        src_dir = args.coref_dir or args.input_dir
        used_coref = bool(args.coref_dir)
        tlabels = None
        if args.things_labels:
            tlabels = {s.strip().upper() for s in args.things_labels.split(',') if s.strip()}
        process_dirs(
            src_dir,
            args.out,
            normalized_dir=args.normalized_dir,
            used_coref=used_coref,
            max_fallback_dates=args.max_fallback_dates,
            things_labels=tlabels,
            min_thing_count=args.min_thing_count,
            allow_other_into_how=args.allow_other_into_how,
        )
        return 0
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1
