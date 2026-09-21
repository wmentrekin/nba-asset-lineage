"""Tests for lineage.fetch: store_payload and the `lineage fetch` CLI verb."""

import hashlib
import json

import pytest

from lineage import cli
from lineage.fetch import store_payload


class FakeCursor:
    def __init__(self, store):
        self._store = store
        self._last_result = None

    def execute(self, sql, params=None):
        sql_lower = sql.lower()
        if "insert into lineage.source_record" in sql_lower:
            _source, source_url, payload, payload_sha256 = params
            if payload_sha256 in self._store:
                self._last_result = None
            else:
                new_id = len(self._store) + 1
                self._store[payload_sha256] = {
                    "id": new_id,
                    "source_url": source_url,
                    "payload": payload,
                }
                self._last_result = (new_id,)
        elif "select id from lineage.source_record" in sql_lower:
            (payload_sha256,) = params
            row = self._store[payload_sha256]
            self._last_result = (row["id"],)
        else:
            raise AssertionError(f"unexpected SQL: {sql}")

    def fetchone(self):
        return self._last_result

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class FakeConnection:
    def __init__(self, store=None):
        self.store = store if store is not None else {}
        self.committed = False

    def cursor(self):
        return FakeCursor(self.store)

    def commit(self):
        self.committed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def test_store_payload_inserts_new_payload():
    conn = FakeConnection()
    raw = json.dumps({"a": 1}).encode()

    source_record_id, inserted = store_payload(conn, raw, "https://example.com/feed.json")

    assert inserted is True
    assert source_record_id == 1
    assert conn.committed is True


def test_store_payload_dedupes_identical_payload():
    conn = FakeConnection()
    raw = json.dumps({"a": 1}).encode()

    first_id, first_inserted = store_payload(conn, raw, "https://example.com/feed.json")
    second_id, second_inserted = store_payload(conn, raw, "https://example.com/feed.json")

    assert first_inserted is True
    assert second_inserted is False
    assert first_id == second_id


def test_store_payload_rejects_invalid_json():
    conn = FakeConnection()
    raw = b"not json"

    with pytest.raises(json.JSONDecodeError):
        store_payload(conn, raw, "https://example.com/feed.json")


def test_fetch_cli_with_payload_file(tmp_path, monkeypatch, capsys):
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps({"NBA_Player_Movement": []}))

    fake_conn = FakeConnection()
    monkeypatch.setattr(cli, "connect", lambda: fake_conn)

    exit_code = cli.main(["fetch", "--payload-file", str(payload_path)])

    assert exit_code == 0
    assert len(fake_conn.store) == 1
    row = next(iter(fake_conn.store.values()))
    assert row["source_url"] == f"file://{payload_path.resolve()}"

    captured = capsys.readouterr()
    assert "source_record id=1 inserted sha=" in captured.out


def test_fetch_cli_save_to_writes_raw_bytes(tmp_path, monkeypatch):
    payload_path = tmp_path / "payload.json"
    raw_text = json.dumps({"NBA_Player_Movement": []})
    payload_path.write_text(raw_text)
    save_path = tmp_path / "out" / "saved.json"

    fake_conn = FakeConnection()
    monkeypatch.setattr(cli, "connect", lambda: fake_conn)

    exit_code = cli.main(
        ["fetch", "--payload-file", str(payload_path), "--save-to", str(save_path)]
    )

    assert exit_code == 0
    assert save_path.read_bytes() == raw_text.encode()
    expected_sha = hashlib.sha256(raw_text.encode()).hexdigest()
    assert expected_sha in fake_conn.store
