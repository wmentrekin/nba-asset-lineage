from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nba_asset_lineage.stages.build_graph import run_build_graph
from nba_asset_lineage.stages.export import run_export
from nba_asset_lineage.stages.ingest import run_ingest
from nba_asset_lineage.stages.normalize import run_normalize


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Memphis asset lineage pipeline")
    parser.add_argument("--start-date", default="2022-05-14")
    parser.add_argument("--end-date", default="2026-02-26")
    parser.add_argument("--team-code", default="MEM")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    context = {
        "start_date": args.start_date,
        "end_date": args.end_date,
        "team_code": args.team_code,
    }

    run_ingest(context)
    run_normalize(context)
    run_build_graph(context)
    run_export(context)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
