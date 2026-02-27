# Silver Field Endpoint Coverage

As-of date: 2026-02-27

This matrix maps each Silver-level field to sourceability via:

- `nba_api` (`swar/nba_api`, NBA.com endpoints)
- `basketball-reference-scraper` (`basketball_reference_scraper`)

Assumption scope for "Silver fields":

- Canonical fields from `src/nba_asset_lineage/models.py`
- Plus inferred operational columns referenced by `sql/migrations/0002_franchise_scope.sql`: `team_id`, `event_order`, `owner_team_id`, `valid_from_date`, `effective_date`, `franchise_id`, `operating_team_id`.

Status legend:

- `yes`: direct field from source endpoint/function
- `partial`: available only for subset of event/asset types or needs inference
- `no`: not available from this source
- `derived`: created deterministically inside pipeline, not directly sourced

## 1) Silver Events Fields

| Silver field | `nba_api` coverage | `nba_api` endpoint(s) | `basketball-reference-scraper` coverage | scraper function(s) | Notes |
|---|---|---|---|---|---|
| `event_id` | derived | n/a | derived | n/a | Deterministic ID (`ids.py`) |
| `event_key` | partial | `drafthistory.DraftHistory` (can derive key for draft rows) | no | n/a | No documented transaction endpoint in `nba_api` stats endpoint catalog |
| `event_date` | no | n/a | no | n/a | `DraftHistory` provides `SEASON`, not exact transaction date |
| `event_type` | partial | `drafthistory.DraftHistory` (draft-related only) | no | n/a | Trade/waiver/signing/extension/conversion not exposed as endpoint family |
| `event_label` | no | n/a | no | n/a | Requires transformation logic + source text |
| `description` | no | n/a | no | n/a | Requires source narrative / transaction log text |
| `source_id` | derived | n/a | derived | n/a | Internal provenance key |
| `source_url` | partial | endpoint URL known (e.g. stats URL) | no | n/a | For transaction-specific URLs, no documented `nba_api` transaction endpoint |
| `team_id` | partial | `commonplayerinfo.CommonPlayerInfo`, `commonteamroster.CommonTeamRoster`, `drafthistory.DraftHistory` | partial | `teams.get_roster`, `drafts.get_draft_class` | Team linkage possible for some records |
| `event_order` | derived | n/a | derived | n/a | Ordering built by pipeline sort rules |
| `franchise_id` | derived | n/a | derived | n/a | Config/mapping-derived |
| `operating_team_id` | partial | `franchisehistory.FranchiseHistory`, `commonteamyears.CommonTeamYears` | partial | team abbreviation from roster/draft tables | Date-level era boundaries need business mapping |

## 2) Silver Asset Fields (AssetSegment)

| Silver field | `nba_api` coverage | `nba_api` endpoint(s) | `basketball-reference-scraper` coverage | scraper function(s) | Notes |
|---|---|---|---|---|---|
| `edge_id` | derived | n/a | derived | n/a | Deterministic lineage edge ID |
| `asset_id` | derived | n/a | derived | n/a | Deterministic from canonical asset key |
| `asset_key` | partial | `commonallplayers.CommonAllPlayers` (`PERSON_ID`), `drafthistory.DraftHistory` | partial | `drafts.get_draft_class`, `teams.get_roster` | Pick-obligation key must be custom |
| `asset_type` | partial | inferred from draft/player data | partial | inferred | Needs event semantics for full fidelity |
| `subtype` | partial | inferred | partial | inferred | Depends on business rules |
| `source_node_id` | derived | n/a | derived | n/a | Built during graph assembly |
| `target_node_id` | derived | n/a | derived | n/a | Built during graph assembly |
| `start_date` | no | n/a | no | n/a | No transaction-date feed in documented endpoints |
| `end_date` | no | n/a | no | n/a | Requires event lifecycle inference |
| `is_active_at_end` | derived | n/a | derived | n/a | Computed |
| `player_name` | yes | `commonallplayers.CommonAllPlayers`, `commonplayerinfo.CommonPlayerInfo` | yes | `teams.get_roster`, `players.get_stats`, `players.get_game_logs` | Readily available |
| `contract_expiry_year` | no | n/a | no | n/a | Not present in documented endpoints/functions |
| `average_annual_salary` | no | n/a | no | n/a | Not present in documented endpoints/functions |
| `acquisition_method` | no | n/a | no | n/a | Needs transaction semantics |
| `original_team` | partial | `drafthistory.DraftHistory` (team at draft selection) | partial | `drafts.get_draft_class` | Future pick original-owner lineage not directly exposed |
| `pick_year` | partial | `drafthistory.DraftHistory` (`SEASON`) | yes | `drafts.get_draft_class(year)` | Only for completed drafts |
| `pick_number` | partial | `drafthistory.DraftHistory` (`OVERALL_PICK`) | yes | `drafts.get_draft_class(year)` (`PICK`) | Future pick assets remain unknown pre-draft |
| `protections_raw` | no | n/a | no | n/a | No documented protections endpoint |
| `protections_structured` | no | n/a | no | n/a | Requires parser + source text not exposed here |
| `swap_conditions_raw` | no | n/a | no | n/a | No documented swap obligation endpoint |
| `swap_conditions_structured` | no | n/a | no | n/a | Requires parser + source text not exposed here |
| `prior_transactions` | no | n/a | no | n/a | No transaction history endpoint/function in these surfaces |

## 3) Silver Event-Asset Lineage Fields

| Silver field | `nba_api` coverage | `nba_api` endpoint(s) | `basketball-reference-scraper` coverage | scraper function(s) | Notes |
|---|---|---|---|---|---|
| `event_id` | derived | n/a | derived | n/a | FK to events |
| `asset_id` | derived | n/a | derived | n/a | FK to assets |
| `action` / `action_raw` | no | n/a | no | n/a | Requires transaction semantics |
| `direction` / `direction_raw` | no | n/a | no | n/a | Requires transaction semantics |
| `effective_date` | no | n/a | no | n/a | Requires transaction date |
| `franchise_id` | derived | n/a | derived | n/a | Config/mapping |

## 4) Franchise/Era Mapping Fields

| Silver field | `nba_api` coverage | `nba_api` endpoint(s) | `basketball-reference-scraper` coverage | scraper function(s) | Notes |
|---|---|---|---|---|---|
| `franchise_id` | derived | n/a | derived | n/a | Internal config |
| `operating_team_id` | partial | `franchisehistory.FranchiseHistory`, `commonteamyears.CommonTeamYears`, static `teams.get_teams()` | partial | team abbreviations from roster/draft outputs | Era boundaries are year-based in endpoint outputs |
| `team_name` | yes | `franchisehistory.FranchiseHistory`, static `teams.get_teams()` | partial | team strings in outputs | Usable |
| `era_start`, `era_end` | partial | `franchisehistory.FranchiseHistory` (`START_YEAR`, `END_YEAR`) | no | n/a | Exact date (not just year) must be policy-mapped |

## 5) Exact Gaps (What You Cannot Fully Get From `nba_api`)

1. Full transaction event stream for trades, waivers, signings, extensions, conversions (no documented stats endpoint family for this in `nba_api` docs).
2. Contract economics fields (`average_annual_salary`, contract term/expiry economics).
3. Pick obligation details (`protections_*`, `swap_conditions_*`) as structured machine-readable historical lineage.
4. Exact per-event dates for non-game transaction events needed to populate `event_date`, `start_date`, `end_date`, `effective_date` at day-level granularity.

## 6) What `basketball-reference-scraper` Adds (and Does Not Add)

Adds useful free coverage for:

- Historical roster snapshots (`teams.get_roster`)
- Historical draft outcomes (`drafts.get_draft_class`)
- Player stat/game-log context (`players.get_stats`, `players.get_game_logs`)

Still missing for Silver lineage completeness:

- Transaction feed (trade/waive/sign/extend/convert)
- Contract/AAV data
- Pick protections/swap obligation logic

## 7) Primary References

- `nba_api` package and docs: https://github.com/swar/nba_api
- `nba_api` complete stats endpoints: https://nba-api-sbang.readthedocs.io/en/latest/nba_api/stats/endpoints/nba_stats_endpoints/
- `DraftHistory` endpoint: https://nba-api-sbang.readthedocs.io/en/latest/nba_api/stats/endpoints/drafthistory/
- `CommonAllPlayers` endpoint: https://nba-api-sbang.readthedocs.io/en/latest/nba_api/stats/endpoints/commonallplayers/
- `CommonPlayerInfo` endpoint: https://nba-api-sbang.readthedocs.io/en/latest/nba_api/stats/endpoints/commonplayerinfo/
- `CommonTeamRoster` endpoint: https://nba-api-sbang.readthedocs.io/en/latest/nba_api/stats/endpoints/commonteamroster/
- `CommonTeamYears` endpoint: https://nba-api-sbang.readthedocs.io/en/latest/nba_api/stats/endpoints/commonteamyears/
- `FranchiseHistory` endpoint: https://nba-api-sbang.readthedocs.io/en/latest/nba_api/stats/endpoints/franchisehistory/
- `basketball-reference-scraper` API surface: https://raw.githubusercontent.com/vishaalagartha/basketball_reference_scraper/master/API.md
- Sports-Reference API position: https://www.sports-reference.com/bot-traffic.html
