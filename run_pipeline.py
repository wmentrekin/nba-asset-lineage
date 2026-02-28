from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pipeline_cli import (  # noqa: E402
    bronze_main,
    gold_main,
    main,
    pipeline_main,
    silver_main,
    visualize_main,
)


if __name__ == "__main__":
    raise SystemExit(main())
