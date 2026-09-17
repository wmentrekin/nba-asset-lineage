"""Command-line entry point for the lineage package."""

import argparse
import sys

from lineage.db import check_db

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

NOT_IMPLEMENTED = {"migrate", "fetch", "derive", "validate", "export", "render", "load"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lineage", description="Memphis Grizzlies asset-lineage MVP")
    subparsers = parser.add_subparsers(dest="verb", required=True)
    for verb in VERBS:
        subparsers.add_parser(verb)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.verb == "check-db":
        check_db()
        return 0

    if args.verb in NOT_IMPLEMENTED:
        print(f"{args.verb}: not implemented yet")
        return 2

    parser.error(f"unknown verb: {args.verb}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
