from __future__ import annotations

import argparse
import os
from typing import Optional, List

from .api import normalize_dir, _resolve


def main(argv: Optional[List[str]] = None) -> int:
    """The main entry point for the command-line interface.

    This function parses command-line arguments and calls `normalize_dir` to
    normalize the documents.

    Args:
        argv: A list of command-line arguments.

    Returns:
        An exit code.
    """
    p = argparse.ArgumentParser(prog="combo normalize", description="Build sentences and chunks from extracted JSON")
    p.add_argument("extracted_json_dir", help="Directory containing extracted JSON files")
    p.add_argument("--out", required=True, help="Output directory for normalized JSONs")
    args = p.parse_args(argv)
    try:
        in_dir = _resolve(args.extracted_json_dir)
        out_dir = _resolve(args.out)
        # Forbid writing inside input directory to avoid clobbering
        if out_dir == in_dir or out_dir.startswith(in_dir + os.sep):
            print("Error: --out must not be inside the input directory.")
            return 2
        outs = normalize_dir(in_dir, out_dir)
        print(f"Wrote {len(outs)} files to {out_dir}")
        return 0
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1
