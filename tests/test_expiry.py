"""Tests for contract expiries (signed elsewhere, curated) and the two-way cap (E8)."""

import copy
import datetime as dt

from lineage.derive import build_graph, graph_to_json
from lineage.events import ExpirationEntry
from lineage.timeline import build_timelines
from lineage.validate import validate_graph

RUPERT_PHI_ROW = {
    "TEAM_ID": 1610612755.0,
    "GroupSort": "Signing 1153050",
    "PLAYER_ID": 1641712.0,
    "TEAM_SLUG": "sixers",
    "PLAYER_SLUG": "rayan-rupert",
    "Additional_Sort": 0.0,
    "TRANSACTION_DATE": "2026-07-08T00:00:00",
    "Transaction_Type": "Signing",
    "TRANSACTION_DESCRIPTION": "Philadelphia 76ers signed guard Rayan Rupert to a Two-Way Contract.",
}
COOPER_TWO_WAY_ROW = {
    "TEAM_ID": 1610612763.0,
    "GroupSort": "Signing 1154418",
    "PLAYER_ID": 1643721.0,
    "TEAM_SLUG": "grizzlies",
    "PLAYER_SLUG": "carson-cooper",
    "Additional_Sort": 0.0,
    "TRANSACTION_DATE": "2026-09-28T00:00:00",
    "Transaction_Type": "Signing",
    "TRANSACTION_DESCRIPTION": "Memphis Grizzlies signed forward Carson Cooper to a Two-Way Contract.",
}
JEROME_ATL_ROW = {
    "TEAM_ID": 1610612737.0,
    "GroupSort": "Signing 1149999",
    "PLAYER_ID": 1629660.0,
    "TEAM_SLUG": "hawks",
    "PLAYER_SLUG": "ty-jerome",
    "Additional_Sort": 0.0,
    "TRANSACTION_DATE": "2026-03-20T00:00:00",
    "Transaction_Type": "Signing",
    "TRANSACTION_DESCRIPTION": "Atlanta Hawks signed guard Ty Jerome to a Contract.",
}
RUPERT_ID = "1641712"


def _build(payload, inputs, rows=()):
    snapshot, curated, corrections = inputs
    payload = copy.deepcopy(payload)
    payload["NBA_Player_Movement"]["rows"] += [dict(row) for row in rows]
    graph = build_graph(payload, snapshot, curated, corrections)
    return graph, validate_graph(graph, snapshot, curated)


def _codes(findings, code):
    return [f for f in findings if f.code == code]


def test_fixture_alone_has_no_signed_elsewhere_expiries(feed_payload, resolvable_inputs):
    graph, findings = _build(feed_payload, resolvable_inputs)

    assert not any(t.id.startswith("Expire-Contract-") for t in graph.transactions)
    assert _codes(findings, "E8") == []
    assert _codes(findings, "W8") == []


def test_rupert_expires_on_june_30_when_philadelphia_signs_him(feed_payload, resolvable_inputs):
    graph, findings = _build(feed_payload, resolvable_inputs, [RUPERT_PHI_ROW])

    expiry = next(t for t in graph.transactions if t.id == "Expire-Contract-1641712-2026")
    assert expiry.kind == "expiry"
    assert expiry.occurred_on == dt.date(2026, 6, 30)
    assert expiry.description == "Contract expired; next signed by PHI on 2026-07-08"
    assert expiry.source_key == "feed"
    movements = [m for m in graph.movements if m.transaction_id == expiry.id]
    assert [(m.asset_id, m.from_holder, m.to_holder, m.contract_type) for m in movements] == [
        (RUPERT_ID, "MEM", "FA", None)
    ]
    assert build_timelines(graph.movements)[("player", RUPERT_ID)][-1].holder == "FA"
    assert [f for f in findings if f.level == "error"] == []
    assert _codes(findings, "W8") == []


def test_in_season_gap_places_the_expiry_on_the_other_teams_date_with_w8(
    feed_payload, resolvable_inputs
):
    graph, findings = _build(feed_payload, resolvable_inputs, [JEROME_ATL_ROW])

    expiry = next(t for t in graph.transactions if t.id == "Expire-Contract-1629660-2026")
    assert expiry.occurred_on == dt.date(2026, 3, 20)
    assert expiry.description == "Contract expired; next signed by ATL on 2026-03-20"
    assert len(_codes(findings, "W8")) == 1
    assert "1629660" in _codes(findings, "W8")[0].message
    assert [f for f in findings if f.level == "error"] == []


def test_rows_about_memphis_from_other_teams_are_ignored(feed_payload, resolvable_inputs):
    row = dict(JEROME_ATL_ROW, Additional_Sort=1610612763.0)

    graph, _ = _build(feed_payload, resolvable_inputs, [row])

    assert not any(t.id.startswith("Expire-Contract-") for t in graph.transactions)


def test_curated_expiration_produces_an_expiry(feed_payload, resolvable_inputs):
    snapshot, curated, corrections = resolvable_inputs
    curated = curated.model_copy(
        update={
            "contract_expirations": [
                ExpirationEntry(
                    player_id=1641712,
                    player_name="Rayan Rupert",
                    date=dt.date(2026, 6, 30),
                    footnotes=["Two-way ran out."],
                )
            ]
        }
    )

    graph, _ = _build(feed_payload, (snapshot, curated, corrections))

    expiry = next(t for t in graph.transactions if t.id == "Expire-Contract-1641712-2026")
    assert expiry.description == "Contract expired (curated) Two-way ran out."
    assert expiry.source_key == "events"


def test_curated_wins_over_the_automatic_rule_for_the_same_player_and_year(
    feed_payload, resolvable_inputs
):
    snapshot, curated, corrections = resolvable_inputs
    entry = ExpirationEntry(
        player_id=1641712, player_name="Rayan Rupert", date=dt.date(2026, 6, 29)
    )
    curated = curated.model_copy(update={"contract_expirations": [entry]})

    graph, findings = _build(feed_payload, (snapshot, curated, corrections), [RUPERT_PHI_ROW])

    expiries = [t for t in graph.transactions if t.id.startswith("Expire-Contract-1641712")]
    assert [(t.id, t.occurred_on, t.source_key) for t in expiries] == [
        ("Expire-Contract-1641712-2026", dt.date(2026, 6, 29), "events")
    ]
    assert [f for f in findings if f.level == "error"] == []


def test_shipped_curated_events_has_an_empty_expiration_list(resolvable_inputs):
    assert resolvable_inputs[1].contract_expirations == []


def test_fourth_two_way_signing_breaches_the_cap(feed_payload, resolvable_inputs):
    _, findings = _build(feed_payload, resolvable_inputs, [COOPER_TWO_WAY_ROW])

    e8 = _codes(findings, "E8")
    assert len(e8) == 1
    assert e8[0].level == "error"
    assert "2026-09-28" in e8[0].message
    assert "Carson Cooper" in e8[0].message and "Rayan Rupert" in e8[0].message


def test_cap_holds_once_rupert_expires_but_not_without_it(feed_payload, resolvable_inputs):
    _, with_expiry = _build(
        feed_payload, resolvable_inputs, [COOPER_TWO_WAY_ROW, RUPERT_PHI_ROW]
    )
    _, without = _build(feed_payload, resolvable_inputs, [COOPER_TWO_WAY_ROW])

    assert _codes(with_expiry, "E8") == []
    assert len(_codes(without, "E8")) == 1


def test_build_is_deterministic_with_the_extra_rows(feed_payload, resolvable_inputs):
    rows = [RUPERT_PHI_ROW, JEROME_ATL_ROW, COOPER_TWO_WAY_ROW]

    first, _ = _build(feed_payload, resolvable_inputs, rows)
    second, _ = _build(feed_payload, resolvable_inputs, rows)

    assert graph_to_json(first) == graph_to_json(second)
