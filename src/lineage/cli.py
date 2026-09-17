"""Command-line entry point for the lineage package."""

import argparse
import pathlib
import sys

from lineage.db import check_db, connect
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

NOT_IMPLEMENTED = {"derive", "validate", "export", "render", "load"}

SQL_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "sql"


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

    if args.verb in NOT_IMPLEMENTED:
        print(f"{args.verb}: not implemented yet")
        return 2

    parser.error(f"unknown verb: {args.verb}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
