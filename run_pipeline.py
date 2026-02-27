from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nba_asset_lineage.scope import load_scope_config
from nba_asset_lineage.settings import DEFAULT_SCOPE_CONFIG_PATH
from nba_asset_lineage.stages.bronze_ingest import run_bronze_ingest
from nba_asset_lineage.stages.gold_publish import run_gold_publish
from nba_asset_lineage.stages.silver_transform import run_silver_transform


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run franchise-wide medallion pipeline scaffold")
    parser.add_argument("--scope-config", type=Path, default=DEFAULT_SCOPE_CONFIG_PATH)
    parser.add_argument("--run-mode", choices=["full", "incremental"], default="full")
    parser.add_argument("--as-of-date", default=date.today().isoformat())
    parser.add_argument("--source-system", default="manual")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    scope = load_scope_config(args.scope_config)

    context = {
        "franchise_id": scope.franchise_id,
        "scope_config_path": str(args.scope_config),
        "start_date": scope.start_date,
        "end_date": scope.end_date,
        "run_mode": args.run_mode,
        "as_of_date": args.as_of_date,
        "source_system": args.source_system,
        "dry_run": "true" if args.dry_run else "false",
    }

    run_bronze_ingest(context)
    run_silver_transform(context)
    run_gold_publish(context)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
