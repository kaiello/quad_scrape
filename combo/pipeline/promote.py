from __future__ import annotations

import os
import sys


def _ensure_src_on_path() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(here))  # project root containing `src/`
    src = os.path.join(root, "src")
    if os.path.isdir(src) and src not in sys.path:
        sys.path.insert(0, src)


_ensure_src_on_path()

from src.combo.pipeline.promote import (  # type: ignore  # noqa: E402
    promote as promote,  # re-export
    main as main,        # CLI entry
)


if __name__ == "__main__":
    raise SystemExit(main())
