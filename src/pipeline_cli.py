from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Sequence

from bronze_ingest import run_bronze_ingest
from gold_publish import run_gold_publish
from scope import load_scope_config
from settings import DEFAULT_BRONZE_RAW_DIR, DEFAULT_EXPORTS_DIR, DEFAULT_SCOPE_CONFIG_PATH
from silver_transform import run_silver_transform
from visualization import write_visualization_html


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run franchise-wide medallion pipeline scaffold")
    parser.add_argument("--stage", choices=["all", "bronze", "silver", "gold", "visualize"], default="all")
    parser.add_argument("--scope-config", type=Path, default=DEFAULT_SCOPE_CONFIG_PATH)
    parser.add_argument("--run-mode", choices=["full", "incremental"], default="full")
    parser.add_argument("--as-of-date", default=date.today().isoformat())
    parser.add_argument("--source-system", default="manual")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_BRONZE_RAW_DIR)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--nodes", type=Path, default=DEFAULT_EXPORTS_DIR / "nodes.csv")
    parser.add_argument("--edges", type=Path, default=DEFAULT_EXPORTS_DIR / "edges.csv")
    parser.add_argument("--output", type=Path, default=DEFAULT_EXPORTS_DIR / "graph_view.html")
    return parser.parse_args(argv)


def _build_context(args: argparse.Namespace) -> dict[str, str]:
    scope = load_scope_config(args.scope_config)
    return {
        "franchise_id": scope.franchise_id,
        "scope_config_path": str(args.scope_config),
        "start_date": scope.start_date,
        "end_date": scope.end_date,
        "run_mode": args.run_mode,
        "as_of_date": args.as_of_date,
        "source_system": args.source_system,
        "raw_dir": str(args.raw_dir),
        "dry_run": "true" if args.dry_run else "false",
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    if args.stage == "visualize":
        output_path = write_visualization_html(output_path=args.output, nodes_path=args.nodes, edges_path=args.edges)
        print(f"Wrote visualization HTML: {output_path}")
        return 0

    context = _build_context(args)

    if args.stage in {"all", "bronze"}:
        run_bronze_ingest(context)
    if args.stage in {"all", "silver"}:
        run_silver_transform(context)
    if args.stage in {"all", "gold"}:
        run_gold_publish(context)
    return 0


def _run_for_stage(stage: str) -> int:
    return main(["--stage", stage, *sys.argv[1:]])


def bronze_main() -> int:
    return _run_for_stage("bronze")


def silver_main() -> int:
    return _run_for_stage("silver")


def gold_main() -> int:
    return _run_for_stage("gold")


def visualize_main() -> int:
    return _run_for_stage("visualize")


def pipeline_main() -> int:
    return _run_for_stage("all")


if __name__ == "__main__":
    raise SystemExit(main())
