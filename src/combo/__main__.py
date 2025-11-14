from __future__ import annotations

import sys


def main() -> int:
    """The main entry point for the combo package."""
    if len(sys.argv) < 2:
        print("Usage: python -m combo <command> [args]")
        return 1

    command = sys.argv[1]
    if command == "embed":
        from combo.embed.cli import main as embed_main
        return embed_main(sys.argv[2:])
    elif command == "er":
        from combo.er.cli import main as er_main
        return er_main(sys.argv[2:])
    elif command == "coref":
        from combo.coref.cli import main as coref_main
        return coref_main(sys.argv[2:])
    elif command == "normalize":
        from combo.normalize.segment import main as normalize_main
        return normalize_main(sys.argv[2:])
    elif command == "validate":
        from combo.normalize.validate import main as validate_main
        return validate_main(sys.argv[2:])
    elif command == "fourw":
        from combo.docprops.aggregate_4w import main as fourw_main
        return fourw_main(sys.argv[2:])
    elif command == "link":
        from combo.link.linker import main as link_main
        return link_main(sys.argv[2:])
    else:
        print(f"Unknown command: {command}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
