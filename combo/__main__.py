"""
Thin CLI shim so you can run `python -m combo ...` without installing.
It forwards to the real implementation in `src.combo.normalize.segment`.
"""
from __future__ import annotations

import os
import sys


def _ensure_src_on_path() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)  # project root containing `src/`
    src = os.path.join(root, "src")
    if os.path.isdir(src) and src not in sys.path:
        sys.path.insert(0, src)


def main() -> int:
    _ensure_src_on_path()
    args = sys.argv[1:]
    # Top-level commands: normalize, validate
    if not args:
        print("Usage: py -m combo [normalize|validate] ...")
        return 2
    cmd = args[0]
    if cmd == "normalize":
        from src.combo.normalize.segment import main as norm_main
        return norm_main(args[1:])
    if cmd == "validate":
        from src.combo.normalize.validate import main as val_main
        return val_main(args[1:])
    if cmd == "embed":
        from src.combo.embed.cli import main as emb_main
        return emb_main(args[1:])
    if cmd == "doctor":
        from src.combo.embed.doctor import main as doc_main
        return doc_main(args[1:])
    if cmd == "index":
        from src.combo.embed.index import main as idx_main
        return idx_main(args[1:])
    if cmd == "er":
        from src.combo.er.cli import main as er_main
        return er_main(args[1:])
    if cmd == "fourw":
        from src.combo.docprops.aggregate_4w import main as fourw_main
        return fourw_main(args[1:])
    if cmd == "link":
        from src.combo.link.linker import main as link_main
        return link_main(args[1:])
    if cmd == "promote":
        from src.combo.pipeline.promote import main as promote_main
        return promote_main(args[1:])
    if cmd == "quarantine":
        # Subcommands: summarize
        if len(args) < 2:
            print("Usage: py -m combo quarantine summarize <quarantine_dir> --out <md> [--json <json>]")
            return 2
        sub = args[1]
        if sub == "summarize":
            from src.combo.pipeline.quarantine import main as qsum_main
            return qsum_main(args[2:])
        print(f"Unknown quarantine subcommand: {sub}")
        return 2
    print(f"Unknown command: {cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
