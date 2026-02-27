from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nba_asset_lineage.settings import DEFAULT_END_DATE, DEFAULT_START_DATE, DEFAULT_TEAM_CODE
from nba_asset_lineage.stages.ingest import run_ingest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ingest stage")
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", default=DEFAULT_END_DATE)
    parser.add_argument("--team-code", default=DEFAULT_TEAM_CODE)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_ingest(
        {
            "start_date": args.start_date,
            "end_date": args.end_date,
            "team_code": args.team_code,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
