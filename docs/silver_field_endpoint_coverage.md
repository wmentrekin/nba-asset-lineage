# Silver Field Endpoint Coverage

As-of date: 2026-02-27

This matrix maps each Silver-level field to sourceability with **Sportradar NBA API as the primary source**, plus secondary/fallback coverage from:

- `nba_api` (`swar/nba_api`, NBA.com endpoints)
- `basketball-reference-scraper` (`basketball_reference_scraper`)

Assumption scope for "Silver fields":

- Canonical event/asset/lineage fields from the current project design specification
- Plus inferred operational columns referenced by `sql/0002_franchise_scope.sql`: `team_id`, `event_order`, `owner_team_id`, `valid_from_date`, `effective_date`, `franchise_id`, `operating_team_id`

Status legend:

- `yes`: direct field from source endpoint payload
- `partial`: available only for subset of records/types or requires deterministic transformation
- `no`: not available from source
- `derived`: computed deterministically inside pipeline

## Primary Sportradar endpoints used in mapping

- `Daily Transfers` (`nba-daily-transfers`)
- `Daily Change Log` (`nba-daily-change-log`)
- `Player Profile` (`nba-player-profile`)
- `Team Profile` (`nba-team-profile`)
- `Draft Summary` (`nba-draft-summary`)
- `Draft Trades` (`nba-trades`)
- `NBA FAQs` (valid `transaction_code` / `transaction_type` list)

## 1) Silver Events Fields

| Silver field | Sportradar coverage | Primary Sportradar endpoint(s) | `nba_api` fallback | `basketball-reference-scraper` fallback | Notes |
|---|---|---|---|---|---|
| `event_id` | derived | n/a | derived | derived | Deterministic internal ID |
| `event_key` | yes | `Daily Transfers.transfer.id`; `Draft Trades.trade.id`; `Draft Summary` pick IDs | partial (`DraftHistory` only) | no | Stable source event key per payload item |
| `event_date` | partial | `Daily Transfers.transfer.effective_date`; draft date from `Draft Summary` context | no (for non-draft transactions) | no | Strong for transfer events; draft event date may require summary-level mapping |
| `event_type` | yes | `Daily Transfers.transaction_type` / `transaction_code`; draft endpoints for `draft_pick` | partial (draft only) | no | Codes include `TRD`, `WA`, `SGN`, `CEXT`, `RSGN`, etc. |
| `event_label` | partial | `Daily Transfers.transfer.desc` | no | no | Transaction narrative available for transfer events |
| `description` | partial | `Daily Transfers.transfer.desc` | no | no | Same caveat as `event_label` |
| `source_id` | derived | n/a | derived | derived | Internal provenance identifier |
| `source_url` | yes | Adapter stores endpoint URL + params | partial | no | Fully controlled by adapter metadata |
| `team_id` | partial | `Daily Transfers.from_team/to_team.reference`; team IDs in `Team Profile` | partial | partial | Team linkage is strong for transfer rows |
| `event_order` | derived | n/a | derived | derived | Deterministic ordering by date + tie-break rules |
| `franchise_id` | derived | n/a | derived | derived | Static scope mapping (`grizzlies`) |
| `operating_team_id` | partial | team aliases from transfer/team feeds | partial | partial | Requires VAN/MEM era policy mapping |

## 2) Silver Asset Fields (AssetSegment)

| Silver field | Sportradar coverage | Primary Sportradar endpoint(s) | `nba_api` fallback | `basketball-reference-scraper` fallback | Notes |
|---|---|---|---|---|---|
| `edge_id` | derived | n/a | derived | derived | Deterministic lineage edge ID |
| `asset_id` | derived | n/a | derived | derived | Deterministic from canonical asset key |
| `asset_key` | partial | Player UUID/reference in `Daily Transfers`/`Player Profile`; pick IDs in draft endpoints | partial | partial | Future pick obligations outside draft context may require synthetic keys |
| `asset_type` | partial | transfer semantics + draft item `type` (`pick`, `future_pick`) | partial | partial | Requires mapping rules from event payload |
| `subtype` | partial | transfer code/type mapping | partial | partial | Business-rule derived subtype |
| `source_node_id` | derived | n/a | derived | derived | Graph construction output |
| `target_node_id` | derived | n/a | derived | derived | Graph construction output |
| `start_date` | partial | `Daily Transfers.effective_date`; draft event context | no | no | Good for transfer-driven assets |
| `end_date` | partial | inferred from later transfer/waive events | no | no | Lifecycle closeout is pipeline-derived from event stream |
| `is_active_at_end` | derived | n/a | derived | derived | Computed from open interval status |
| `player_name` | yes | `Daily Transfers.player.full_name`; `Player Profile.full_name` | yes | yes | Fully sourceable |
| `contract_expiry_year` | no | n/a | no | no | Not documented in these endpoints |
| `average_annual_salary` | partial | `Player Profile.salary` / `Team Profile.players[].salary` | no | no | `salary` is current base annual salary, not full-contract AAV |
| `acquisition_method` | partial | `transaction_type` / `transaction_code` | no | no | Requires controlled mapping table |
| `original_team` | partial | draft endpoints (`Draft Summary` / `Draft Trades`) | partial | partial (`get_draft_class`) | Strongest for completed draft picks |
| `pick_year` | partial | `Draft Summary` and `Draft Trades.items[].future_pick.year` | partial | yes (`get_draft_class`) | Future obligations not always fully represented outside draft feeds |
| `pick_number` | partial | `Draft Summary` / `Draft Trades.items[].pick.number/overall` | partial | yes (`get_draft_class`) | Unknown for future unexercised picks |
| `protections_raw` | no | n/a | no | no | No protections field documented in mapped endpoints |
| `protections_structured` | no | n/a | no | no | Cannot be built without a protections source |
| `swap_conditions_raw` | no | n/a | no | no | No swap conditions field documented in mapped endpoints |
| `swap_conditions_structured` | no | n/a | no | no | Cannot be built without a swap source |
| `prior_transactions` | partial | derived from chronological `Daily Transfers` history | no | no | Works only within available coverage window |

## 3) Silver Event-Asset Lineage Fields

| Silver field | Sportradar coverage | Primary Sportradar endpoint(s) | `nba_api` fallback | `basketball-reference-scraper` fallback | Notes |
|---|---|---|---|---|---|
| `event_id` | derived | n/a | derived | derived | FK to events |
| `asset_id` | derived | n/a | derived | derived | FK to assets |
| `action` / `action_raw` | yes | `transaction_type` / `transaction_code` | no | no | Directly mapped for transfer events |
| `direction` / `direction_raw` | partial | `from_team` and `to_team` in transfer payload | no | no | Some transaction types may be one-sided (`waive`, `sign`) |
| `effective_date` | yes | `Daily Transfers.effective_date` | no | no | Day-level date provided |
| `franchise_id` | derived | n/a | derived | derived | Config-mapped |

## 4) Franchise/Era Mapping Fields

| Silver field | Sportradar coverage | Primary Sportradar endpoint(s) | `nba_api` fallback | `basketball-reference-scraper` fallback | Notes |
|---|---|---|---|---|---|
| `franchise_id` | derived | n/a | derived | derived | Internal config |
| `operating_team_id` | partial | team alias/reference from transfer/team feeds | partial | partial | Requires explicit VAN->MEM era date mapping |
| `team_name` | yes | `Team Profile` / league hierarchy feeds | yes | partial | Directly sourceable |
| `era_start`, `era_end` | no | n/a | partial (year-level history) | no | Must be policy-defined dates in scope config |

## 5) Remaining Hard Gaps (even with Sportradar primary)

1. `contract_expiry_year` (not directly documented in mapped endpoints).
2. True contract `average_annual_salary` for full contract term (Sportradar `salary` is current base annual salary).
3. `protections_raw`, `protections_structured`, `swap_conditions_raw`, `swap_conditions_structured`.
4. Full franchise history requirement from `1995-06-23`: Sportradar NBA historical data is documented back to the 2013 season, leaving a 1995-2012 historical gap.

## 6) Source and Terms Notes

- Sportradar endpoints require API key auth (`x-api-key`).
- `basketball-reference-scraper` is still scraping Sports-Reference pages; usage must respect Sports-Reference restrictions.
- `nba_api` remains useful for player/team/draft primitives, but not as complete transaction+contract lineage source.

## 7) References

Sportradar:

- Daily Transfers: https://developer.sportradar.com/basketball/reference/nba-daily-transfers
- Daily Change Log: https://developer.sportradar.com/basketball/reference/nba-daily-change-log
- NBA roster + transaction workflow examples (`effective_date`, `transaction_type`, `transaction_code`, `from_team`, `to_team`): https://developer.sportradar.com/basketball/docs/nba-ig-rosters
- Draft integration guide (`Trades` feed with `items`, `pick`, `future_pick`): https://developer.sportradar.com/basketball/docs/nba-ig-draft
- Draft Trades endpoint: https://developer.sportradar.com/basketball/reference/nba-trades
- Draft Summary endpoint: https://developer.sportradar.com/basketball/reference/nba-draft-summary
- Player Profile endpoint: https://developer.sportradar.com/basketball/reference/nba-player-profile
- Team Profile endpoint: https://developer.sportradar.com/basketball/reference/nba-team-profile
- Salary field changelog (`player.salary` is current base annual salary): https://developer.sportradar.com/sportradar-updates/changelog/nba-api-player-salary-info
- Historical data window (NBA data back to 2013 season): https://developer.sportradar.com/basketball/docs/nba-ig-historical-data
- Transaction code/type list (FAQ): https://developer.sportradar.com/basketball/v4/reference/nba-faq

Secondary sources:

- `nba_api` endpoint catalog: https://nba-api-sbang.readthedocs.io/en/latest/nba_api/stats/endpoints/nba_stats_endpoints/
- `basketball-reference-scraper` package page: https://pypi.org/project/basketball-reference-scraper/
- `basketball-reference-scraper` API surface: https://raw.githubusercontent.com/vishaalagartha/basketball_reference_scraper/master/API.md
- Sports-Reference bot/data policy: https://www.sports-reference.com/bot-traffic.html
