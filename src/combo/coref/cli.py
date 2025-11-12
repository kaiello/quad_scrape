from __future__ import annotations

import argparse
from typing import Optional, List

from .api import process_er_dir


def main(argv: Optional[List[str]] = None) -> int:
    """The main entry point for the command-line interface.

    This function parses command-line arguments and calls `process_er_dir`
    to perform coreference resolution.

    Args:
        argv: A list of command-line arguments.

    Returns:
        An exit code.
    """
    ap = argparse.ArgumentParser(prog='combo coref', description='Within-document coreference (heuristic)')
    ap.add_argument('er_dir', help='Directory with *.entities.jsonl')
    ap.add_argument('--out', required=True, help='Output directory for coref results')
    ap.add_argument('--max-sent-back', type=int, default=3)
    ap.add_argument('--max-mentions-back', type=int, default=30)
    args = ap.parse_args(argv)
    try:
        process_er_dir(args.er_dir, args.out, args.max_sent_back, args.max_mentions_back)
        return 0
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1
