"""Tests for sql/0001_lineage.sql and lineage.migrate.apply_migrations."""

import re
from pathlib import Path

from lineage.migrate import apply_migrations

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"
SQL_FILE = SQL_DIR / "0001_lineage.sql"


def test_exactly_five_lineage_tables():
    text = SQL_FILE.read_text()
    matches = re.findall(
        r"create table if not exists lineage\.\w+", text, flags=re.IGNORECASE
    )
    assert len(matches) == 5


def test_every_create_statement_is_idempotent():
    text = SQL_FILE.read_text()
    schema_statements = re.findall(r"create schema[^;]*;", text, flags=re.IGNORECASE)
    table_statements = re.findall(r"create table[^;]*;", text, flags=re.IGNORECASE)
    index_statements = re.findall(r"create index[^;]*;", text, flags=re.IGNORECASE)

    assert schema_statements and table_statements and index_statements

    for statement in schema_statements + table_statements + index_statements:
        assert "if not exists" in statement.lower()


class FakeCursor:
    def __init__(self, executed):
        self.executed = executed

    def execute(self, sql):
        self.executed.append(sql)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class FakeConnection:
    def __init__(self):
        self.executed = []
        self.committed = False

    def cursor(self):
        return FakeCursor(self.executed)

    def commit(self):
        self.committed = True


def test_apply_migrations_executes_each_sql_file_and_commits(tmp_path):
    (tmp_path / "0001_a.sql").write_text("create table if not exists a (id int);")
    (tmp_path / "0002_b.sql").write_text("create table if not exists b (id int);")

    conn = FakeConnection()
    apply_migrations(conn, tmp_path)

    assert conn.executed == [
        "create table if not exists a (id int);",
        "create table if not exists b (id int);",
    ]
    assert conn.committed is True


def test_apply_migrations_reads_sql_dir_in_sorted_order(tmp_path):
    (tmp_path / "0002_second.sql").write_text("-- second")
    (tmp_path / "0001_first.sql").write_text("-- first")

    conn = FakeConnection()
    apply_migrations(conn, tmp_path)

    assert conn.executed == ["-- first", "-- second"]
