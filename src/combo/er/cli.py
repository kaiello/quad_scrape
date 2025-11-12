from __future__ import annotations

import argparse
from typing import Optional, List

from .api import process_embedded


def main(argv: Optional[List[str]] = None) -> int:
    """The main entry point for the command-line interface.

    This function parses command-line arguments and calls `process_embedded`
    to extract entities and relations.

    Args:
        argv: A list of command-line arguments.

    Returns:
        An exit code.
    """
    ap = argparse.ArgumentParser(prog='combo er', description='Entity/Relation extraction (simple)')
    ap.add_argument('embedded_dir', help='Directory of *.embedded.jsonl')
    ap.add_argument('--normalized-dir', required=True, help='Directory of normalized JSON to supply chunk text')
    ap.add_argument('--out', required=True, help='Output directory for ER JSONLs')
    args = ap.parse_args(argv)
    try:
        counts = process_embedded(args.embedded_dir, args.normalized_dir, args.out)
        print(f"Wrote ER: files={counts['files']} entities={counts['entities']} rels={counts['relations']}")
        return 0
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1
