"""Fetches the raw NBA player-movement feed and stores it verbatim."""

import hashlib
import json

import httpx
import psycopg

FEED_URL = "https://stats.nba.com/js/data/playermovement/NBA_Player_Movement.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.nba.com/",
    "Origin": "https://www.nba.com",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_payload(url: str) -> bytes:
    """GET `url` with browser-like headers and a 30s timeout; raise on non-200."""
    response = httpx.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.content


def store_payload(
    conn: psycopg.Connection,
    raw: bytes,
    source_url: str,
    source: str = "nba_player_movement",
) -> tuple[int, bool]:
    """Validate `raw` as JSON, then insert it as a source_record (deduped by sha256).

    Returns (source_record_id, inserted) where inserted is False if an
    identical payload was already stored.
    """
    payload = json.loads(raw)
    payload_sha256 = hashlib.sha256(raw).hexdigest()

    with conn.cursor() as cur:
        cur.execute(
            """
            insert into lineage.source_record (source, source_url, payload, payload_sha256)
            values (%s, %s, %s, %s)
            on conflict (payload_sha256) do nothing
            returning id
            """,
            (source, source_url, json.dumps(payload), payload_sha256),
        )
        row = cur.fetchone()
        if row is not None:
            conn.commit()
            source_record_id = row[0]
            inserted = True
        else:
            cur.execute(
                "select id from lineage.source_record where payload_sha256 = %s",
                (payload_sha256,),
            )
            source_record_id = cur.fetchone()[0]
            inserted = False

    status = "inserted" if inserted else "already-present"
    print(f"source_record id={source_record_id} {status} sha={payload_sha256[:12]}")
    return source_record_id, inserted
