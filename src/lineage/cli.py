"""Command-line entry point for the lineage package."""

import argparse
import json
import pathlib
import sys

from lineage.db import check_db, connect
from lineage.derive import (
    CURATED_SOURCES,
    DERIVE_ERRORS,
    build_graph,
    graph_to_json,
    load_graph,
    load_inputs,
    print_counts,
    select_feed_payload,
)
from lineage.fetch import FEED_URL, fetch_payload, store_payload
from lineage.migrate import apply_migrations

VERBS = [
    "check-db",
    "migrate",
    "fetch",
    "derive",
    "validate",
    "export",
    "render",
    "load",
]

NOT_IMPLEMENTED = {"validate", "export", "render", "load"}

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
SQL_DIR = REPO_ROOT / "sql"
DATA_DIR = REPO_ROOT / "data"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lineage", description="Memphis Grizzlies asset-lineage MVP")
    subparsers = parser.add_subparsers(dest="verb", required=True)
    for verb in VERBS:
        sub = subparsers.add_parser(verb)
        if verb == "fetch":
            sub.add_argument(
                "--payload-file",
                help="Read the feed payload from this path instead of the network",
            )
            sub.add_argument(
                "--save-to",
                help="Also write the raw payload bytes to this path",
            )
        if verb == "derive":
            sub.add_argument(
                "--feed-fixture",
                help="Read the feed payload from this path and skip the database entirely",
            )
            sub.add_argument(
                "--dry-run",
                action="store_true",
                help="Print the derived rows as JSON instead of loading them",
            )
    return parser


def _run_fetch(args: argparse.Namespace) -> int:
    if args.payload_file:
        payload_path = pathlib.Path(args.payload_file)
        raw = payload_path.read_bytes()
        source_url = f"file://{payload_path.resolve()}"
    else:
        raw = fetch_payload(FEED_URL)
        source_url = FEED_URL

    if args.save_to:
        save_path = pathlib.Path(args.save_to)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_bytes(raw)

    with connect() as conn:
        store_payload(conn, raw, source_url)
    return 0


def _run_derive(args: argparse.Namespace) -> int:
    snapshot, pick_events, corrections = load_inputs(DATA_DIR)

    if args.feed_fixture:
        feed_payload = json.loads(pathlib.Path(args.feed_fixture).read_text())
        graph = build_graph(feed_payload, snapshot, pick_events, corrections)
        if args.dry_run:
            print(graph_to_json(graph))
        else:
            print_counts(graph)
        return 0

    with connect() as conn:
        source_record_ids = {
            source_key: store_payload(
                conn,
                (DATA_DIR / filename).read_bytes(),
                f"file://data/{filename}",
                source,
            )[0]
            for source_key, (source, filename) in CURATED_SOURCES.items()
        }
        feed_record_id, feed_payload = select_feed_payload(conn)
        source_record_ids["feed"] = feed_record_id
        graph = build_graph(feed_payload, snapshot, pick_events, corrections)
        if args.dry_run:
            print(graph_to_json(graph))
            return 0
        load_graph(conn, graph, source_record_ids)
    print_counts(graph)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.verb == "check-db":
        check_db()
        return 0

    if args.verb == "migrate":
        with connect() as conn:
            apply_migrations(conn, SQL_DIR)
        return 0

    if args.verb == "fetch":
        return _run_fetch(args)

    if args.verb == "derive":
        try:
            return _run_derive(args)
        except DERIVE_ERRORS as exc:
            print(f"derive failed: {exc}", file=sys.stderr)
            return 1

    if args.verb in NOT_IMPLEMENTED:
        print(f"{args.verb}: not implemented yet")
        return 2

    parser.error(f"unknown verb: {args.verb}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
