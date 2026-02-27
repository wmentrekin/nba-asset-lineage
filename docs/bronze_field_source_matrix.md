# Bronze Field Source Matrix

As-of date: 2026-02-27

Purpose: field-level mapping from ingestion source -> Bronze raw fields, with terms posture and completeness risk before adapter implementation.

## 1) `bronze.raw_events`

| Bronze field | Required | Meaning | Primary source candidate | API key | Terms posture | Completeness risk |
|---|---:|---|---|---:|---|---|
| `source_system` | yes | System label (`nba_com`, `balldontlie`, etc.) | Adapter config | no | Internal metadata | low |
| `source_event_ref` | yes | Stable source-native event id/key | NBA transactions feed event id; fallback deterministic hash of canonical source URL + date + title | no | NBA terms apply | medium |
| `event_date_raw` | no | Raw event date string from source | NBA transactions date field | no | NBA terms apply | medium |
| `event_type_raw` | no | Raw event type label from source | NBA transactions category/type text | no | NBA terms apply | medium |
| `source_url` | no | URL for provenance | NBA transaction URL / article URL | no | attribution/provenance | low |
| `source_payload` | no | Full unmodified source row | API JSON record or parsed row object | depends | source terms apply | low |

## 2) `bronze.raw_assets`

| Bronze field | Required | Meaning | Primary source candidate | API key | Terms posture | Completeness risk |
|---|---:|---|---|---:|---|---|
| `source_system` | yes | System label | Adapter config | no | Internal metadata | low |
| `source_asset_ref` | yes | Stable source-native asset id | Players: NBA `PERSON_ID` where available; Picks: deterministic obligation key | no | NBA terms for IDs from NBA sources | medium |
| `asset_type_raw` | no | Raw asset type | Derived from event payload (`player`, `future_draft_pick`, etc.) | no | source terms apply | medium |
| `effective_date_raw` | no | Date asset state became effective | Event date from source | no | source terms apply | medium |
| `source_payload` | no | Raw asset payload | Event-derived asset payload or contract API payload | depends | source terms apply | medium |

## 3) `bronze.raw_event_asset_links`

| Bronze field | Required | Meaning | Primary source candidate | API key | Terms posture | Completeness risk |
|---|---:|---|---|---:|---|---|
| `source_system` | yes | System label | Adapter config | no | Internal metadata | low |
| `source_event_ref` | yes | Source event key | From `raw_events` source row | no | source terms apply | low |
| `source_asset_ref` | yes | Source asset key | From `raw_assets` source row | no | source terms apply | low |
| `action_raw` | no | Source action verb (`acquire`, `waive`, etc.) | Parsed from transaction payload text/fields | no | source terms apply | high |
| `direction_raw` | no | In/Out/Modify direction | Derived from event semantics | no | Internal derivation | high |
| `effective_date_raw` | no | Link effective date | Event date | no | source terms apply | medium |
| `source_payload` | no | Raw link payload | Event-asset relation record | no | source terms apply | low |

## 4) Coverage Gaps That Affect Silver Completeness

These are the known blockers to full Silver quality, even if Bronze ingest is technically complete:

| Silver concept | Current free-source status | Why this is a gap | Candidate solutions |
|---|---|---|---|
| Contract AAV (`average_annual_salary`) | Not reliably available from NBA public endpoints alone | NBA releases often do not publish terms; nba_api stats catalog has no contract endpoints | 1) balldontlie contracts endpoints (paid GOAT tier), 2) SportsDataIO paid feeds |
| Contract expiry year | Partial | Some endpoints provide season/roster data but not full signed contract terms | Same as above |
| Pick protections / swap logic | Partial and often text-only | No single officially documented NBA machine-readable historical obligation feed | Parse official trade tracker/article text + manual validation, or licensed provider |
| Full historical transaction depth to 1995 | Not yet proven from NBA feed docs | Official public docs do not clearly publish an earliest transaction-date guarantee | Add a coverage probe script and persist min/max discovered dates |

## 5) Terms and Source Posture (Decision Use)

| Source | API key required | Automation posture |
|---|---:|---|
| NBA.com / nba_api | no | Allowed for controlled ingestion, but governed by NBA Terms (private/non-commercial and anti-database constraints) |
| balldontlie | yes | Allowed via official API only; pay attention to redistribution/caching limits |
| SportsDataIO | yes | Licensed/commercial path; strongest legal posture for scaling |
| Sports-Reference / Basketball-Reference | n/a | No official API; automated extraction is constrained by their terms/data use policy |

## 6) Definitive-Coverage Note

For NBA transaction history specifically, official docs do not provide a single canonical statement of minimum historical date coverage. To make this definitive for your pipeline, treat coverage as a measured metadata artifact:

- Run a read-only coverage probe against the exact transaction endpoints used by your adapter.
- Record: `min_event_date`, `max_event_date`, `records_count`, and endpoint version hash.
- Persist probe output in `data/bronze/checkpoints/source_coverage_<source>.json`.

This converts unknown historical depth into reproducible evidence.
