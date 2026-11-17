"""Database connection helpers for the lineage package."""

import psycopg

from lineage.config import get_database_url


def connect() -> psycopg.Connection:
    """Return a new connection to the configured database."""
    return psycopg.connect(get_database_url())


def check_db() -> None:
    """Run `select 1` against the configured database and print the result."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("select 1")
            cur.fetchone()
    print("db ok")
