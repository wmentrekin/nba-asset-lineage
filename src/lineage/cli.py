"""Command-line entry point for the lineage package."""

import argparse
import json
import pathlib
import sys

import psycopg

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
from lineage.export import run_export
from lineage.fetch import FEED_URL, fetch_payload, store_payload
from lineage.migrate import apply_migrations
from lineage.render import run_render
from lineage.validate import run_validate

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

# RuntimeError: DATABASE_URL missing (lineage.config.get_database_url). OperationalError:
# psycopg couldn't reach or authenticate to the configured database. Both are ordinary,
# expected failure modes for every DB-touching verb, so the CLI reports them the same way
# it reports a DERIVE_ERRORS failure: one line, no traceback.
DB_ERRORS = (RuntimeError, psycopg.OperationalError)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
SQL_DIR = REPO_ROOT / "sql"
DATA_DIR = REPO_ROOT / "data"
DEFAULT_EXPORT_PATH = REPO_ROOT / "exports" / "graph.json"
DEFAULT_RENDER_PATH = REPO_ROOT / "exports" / "graph.svg"


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
        if verb == "validate":
            sub.add_argument(
                "--feed-fixture",
                help="Validate a graph built from this feed payload instead of the database",
            )
            sub.add_argument(
                "--strict",
                action="store_true",
                help="Exit non-zero if there are any warnings, not just errors",
            )
        if verb == "export":
            sub.add_argument(
                "--feed-fixture",
                help="Export a graph built from this feed payload instead of the database",
            )
            sub.add_argument(
                "--out",
                default=str(DEFAULT_EXPORT_PATH),
                help="Where to write graph.json (default: exports/graph.json)",
            )
        if verb == "render":
            sub.add_argument(
                "--in",
                dest="in_path",
                default=str(DEFAULT_EXPORT_PATH),
                help="graph.json to render (default: exports/graph.json)",
            )
            sub.add_argument(
                "--out",
                default=str(DEFAULT_RENDER_PATH),
                help="Where to write graph.svg (default: exports/graph.svg)",
            )
        if verb == "load":
            sub.add_argument(
                "--feed-fixture",
                help="Run fetch+derive+validate+export+render offline from this feed payload",
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


def _run_load(args: argparse.Namespace) -> int:
    """fetch (unless a fixture is given) -> derive -> validate -> export -> render, fail fast."""
    if not args.feed_fixture:
        raw = fetch_payload(FEED_URL)
        with connect() as conn:
            store_payload(conn, raw, FEED_URL)

    derive_rc = _run_derive(argparse.Namespace(feed_fixture=args.feed_fixture, dry_run=False))
    if derive_rc != 0:
        return derive_rc

    validate_rc = run_validate(args.feed_fixture, DATA_DIR, strict=False)
    if validate_rc != 0:
        return validate_rc

    run_export(args.feed_fixture, DATA_DIR, DEFAULT_EXPORT_PATH)
    run_render(DEFAULT_EXPORT_PATH, DEFAULT_RENDER_PATH)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.verb == "check-db":
        try:
            check_db()
            return 0
        except DB_ERRORS as exc:
            print(f"check-db failed: {exc}", file=sys.stderr)
            return 1

    if args.verb == "migrate":
        try:
            with connect() as conn:
                apply_migrations(conn, SQL_DIR)
            return 0
        except DB_ERRORS as exc:
            print(f"migrate failed: {exc}", file=sys.stderr)
            return 1

    if args.verb == "fetch":
        try:
            return _run_fetch(args)
        except DB_ERRORS as exc:
            print(f"fetch failed: {exc}", file=sys.stderr)
            return 1

    if args.verb == "derive":
        try:
            return _run_derive(args)
        except (*DERIVE_ERRORS, *DB_ERRORS) as exc:
            print(f"derive failed: {exc}", file=sys.stderr)
            return 1

    if args.verb == "validate":
        try:
            return run_validate(args.feed_fixture, DATA_DIR, args.strict)
        except (*DERIVE_ERRORS, *DB_ERRORS) as exc:
            print(f"validate failed: {exc}", file=sys.stderr)
            return 1

    if args.verb == "export":
        try:
            run_export(args.feed_fixture, DATA_DIR, pathlib.Path(args.out))
            return 0
        except (*DERIVE_ERRORS, *DB_ERRORS) as exc:
            print(f"export failed: {exc}", file=sys.stderr)
            return 1

    if args.verb == "render":
        run_render(pathlib.Path(args.in_path), pathlib.Path(args.out))
        return 0

    if args.verb == "load":
        try:
            return _run_load(args)
        except (*DERIVE_ERRORS, *DB_ERRORS) as exc:
            print(f"load failed: {exc}", file=sys.stderr)
            return 1

    parser.error(f"unknown verb: {args.verb}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
