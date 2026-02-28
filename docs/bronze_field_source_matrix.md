# Bronze Field Source Matrix

As-of date: 2026-02-27

Purpose: field-level mapping from source -> Bronze raw fields, with **Sportradar as primary source** and explicit notes on completeness and terms posture.

Status legend:

- `yes`: directly sourceable from endpoint payload
- `partial`: available for subset or requires deterministic transform
- `derived`: internal pipeline field
- `no`: not available from source

## 1) `bronze.raw_events`

| Bronze field | Required | Primary source | Endpoint/field mapping | Coverage | Notes |
|---|---:|---|---|---|---|
| `source_system` | yes | adapter metadata | literal `sportradar` | derived | Controlled by adapter |
| `source_event_ref` | yes | Sportradar | `Daily Transfers.transfer.id`; `Draft Trades.trade.id`; draft item IDs | yes | Stable source-native identifiers |
| `event_date_raw` | no | Sportradar | `Daily Transfers.transfer.effective_date`; draft date context | partial | Strong for transfer events |
| `event_type_raw` | no | Sportradar | `transaction_type` / `transaction_code`; draft event mapping | yes | Includes trade/waive/signing code coverage |
| `source_url` | no | adapter metadata | canonical endpoint URL + query params | yes | Required for provenance |
| `source_payload` | no | Sportradar | full JSON row | yes | Stored raw for replay/debug |

Secondary fallback:

- `nba_api`: draft-only event scaffolding (`DraftHistory`)
- `basketball-reference-scraper`: no reliable transaction feed

## 2) `bronze.raw_assets`

| Bronze field | Required | Primary source | Endpoint/field mapping | Coverage | Notes |
|---|---:|---|---|---|---|
| `source_system` | yes | adapter metadata | literal `sportradar` | derived | Controlled by adapter |
| `source_asset_ref` | yes | Sportradar | player UUID/reference; draft pick/future_pick IDs or deterministic keys | partial | Future obligations may need deterministic synthetic keys |
| `asset_type_raw` | no | Sportradar | derived from transfer/draft payload item type | partial | Requires mapping table |
| `effective_date_raw` | no | Sportradar | transfer `effective_date`; draft event date | partial | Good for transfer lifecycle |
| `source_payload` | no | Sportradar | full raw asset object | yes | Preserves raw lineage evidence |

Secondary fallback:

- `nba_api`: player and draft identity primitives
- `basketball-reference-scraper`: draft outcomes and rosters

## 3) `bronze.raw_event_asset_links`

| Bronze field | Required | Primary source | Endpoint/field mapping | Coverage | Notes |
|---|---:|---|---|---|---|
| `source_system` | yes | adapter metadata | literal `sportradar` | derived | Controlled by adapter |
| `source_event_ref` | yes | Sportradar | transfer/trade id from event payload | yes | FK to `raw_events` source key |
| `source_asset_ref` | yes | Sportradar | player/pick key from related payload item | partial | May require deterministic pick keys |
| `action_raw` | no | Sportradar | mapped from `transaction_type` / `transaction_code` | yes | Strong for transfer events |
| `direction_raw` | no | Sportradar | inferred from `from_team` / `to_team` and transaction semantics | partial | One-sided events require rule mapping |
| `effective_date_raw` | no | Sportradar | transfer `effective_date` | yes | Day-level timestamping |
| `source_payload` | no | Sportradar | full relation row object | yes | Debuggable lineage trail |

## 4) Bronze Completeness Risks (pre-Silver)

| Concern | Status with Sportradar primary | Impact on Bronze |
|---|---|---|
| Pre-2013 history | gap | Sportradar historical NBA coverage documented back to 2013 season; 1995-2012 requires supplement |
| Contract term details | partial | Salary exists, but full-contract AAV and expiry are not fully available in mapped endpoints |
| Pick protections/swaps | gap | No documented structured protections/swap fields in mapped endpoints |
| Draft/event date normalization | partial | Some draft contexts may require endpoint crosswalk for exact day-level `event_date_raw` |

## 5) Terms/Access Posture

| Source | Key required | Automation posture |
|---|---:|---|
| Sportradar NBA API | yes | Preferred primary source; governed by account license/usage terms |
| nba_api (NBA endpoints) | no | Useful fallback primitives; governed by NBA terms |
| basketball-reference-scraper | no key | Use with caution due Sports-Reference scraping restrictions |

## 6) References

- Sportradar overview: https://developer.sportradar.com/basketball/docs/nba-ig-overview
- Daily Transfers: https://developer.sportradar.com/basketball/reference/nba-daily-transfers
- Daily Change Log: https://developer.sportradar.com/basketball/reference/nba-daily-change-log
- NBA roster/transaction workflow: https://developer.sportradar.com/basketball/docs/nba-ig-rosters
- Draft integration (trades/picks): https://developer.sportradar.com/basketball/docs/nba-ig-draft
- Draft Trades endpoint: https://developer.sportradar.com/basketball/reference/nba-trades
- Draft Summary endpoint: https://developer.sportradar.com/basketball/reference/nba-draft-summary
- NBA historical window: https://developer.sportradar.com/basketball/docs/nba-ig-historical-data
- nba_api endpoint catalog: https://nba-api-sbang.readthedocs.io/en/latest/nba_api/stats/endpoints/nba_stats_endpoints/
- basketball-reference-scraper package: https://pypi.org/project/basketball-reference-scraper/
