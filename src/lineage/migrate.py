"""Applies SQL migrations to the configured database."""

from pathlib import Path

import psycopg


def apply_migrations(conn: psycopg.Connection, sql_dir: Path) -> None:
    """Read `sql_dir/*.sql` in sorted order and execute each inside one transaction."""
    sql_files = sorted(Path(sql_dir).glob("*.sql"))
    with conn.cursor() as cur:
        for sql_file in sql_files:
            cur.execute(sql_file.read_text())
            print(f"applied {sql_file.name}")
    conn.commit()
