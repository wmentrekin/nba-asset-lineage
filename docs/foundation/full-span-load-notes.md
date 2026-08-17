# Full-Span Load Notes

## Next refresh: safety-tooling handoff

This document records the last verified live baseline; it is **not** permission
to rerun a live load. The parent 2026 offseason refresh remains blocked until
the safe-refresh-tooling PR is reviewed and its verification is complete.

For that later, separately authorized pass:

1. create the restricted repo-local `tmp/<refresh-id>/` leaf and capture the
   fixed 21-table snapshot only when the later live checkpoint authorizes it;
2. capture each required source once into that leaf's fixed bundle slots,
   materialize the four fixed fixture slots, then construct the closed
   `refresh-request.json`, `refresh-reconciliation.json`, and
   `refresh-plan.json` artifacts with their reviewed digests;
3. run `preview-refresh-projection --artifact-directory <leaf>`. It validates
   those local files before its one read-only baseline and writes the sealed,
   sanitized `projection-report.json`; it writes no database rows;
4. review blockers, diffs, reconciliation evidence, and checksums. Record an
   explicit human `execute_refresh` approval bound to the exact artifact chain,
   snapshot, code, environment, dirty tree, schema, database, and prefix
   fingerprints;
5. only after a distinct user go-ahead, run
   `run-approved-foundation-refresh --artifact-directory <leaf> --execute`.
   If a prefix cannot be reconciled, stop in `needs_restore` rather than
   guessing;
6. restore only with separately recorded `action=restore_snapshot` approval,
   explicit future authorization, and
   `restore-foundation-refresh-snapshot --artifact-directory <leaf> --execute`.
   An execution approval never authorizes destructive recovery.

Do not put raw source bodies, snapshot rows, credentials, or local operational
artifacts in this document, a commit, or a PR. See
[`safe-refresh-tooling/`](safe-refresh-tooling/) for the full contracts.

Last verified live load scope:

- team: Memphis Grizzlies
- transaction seasons: 2016-17 through 2025-26
- draft years: 2016 through 2025
- source span in export: 2016-06-23 through 2026-04-10
- currentness source review: no later public Memphis roster event verified
  through 2026-05-29

Latest currentness refresh:

- reran live NBA.com player-movement review on 2026-05-29
- live endpoint metadata reported `Last-Modified: Fri, 29 May 2026 20:34:14 GMT`
- Memphis-filtered date range still ended on `2026-04-10`
- Basketball-Reference `2025-26 MEM transactions` and CBS Memphis transactions
  remained aligned with `2026-04-10` as the latest public Memphis roster event
- no post-`2026-04-10` Memphis roster transaction was found to load

Current live `foundation` counts after the full-span rebuild plus contextual
seed enrichments plus the latest corroboration closeout work:

- `source_record`: 677
- `source_event`: 1019
- `player`: 229
- `player_alias`: 1
- `pick`: 137
- `asset`: 366
- `roster_baseline_player`: 222
- `roster_snapshot`: 40
- `roster_snapshot_player`: 636
- `roster_snapshot_pick`: 980
- `roster_snapshot_validation`: 40
- `daily_roster_state`: 3652
- `daily_roster_state_player`: 61979
- `draft_selection`: 20
- `draft_pick_resolution`: 20
- `draft_prior_owner_lineage`: 20
- `draft_lottery_result`: 5
- `canonical_event`: 407
- `canonical_event_member`: 420
- `event_asset_transition`: 568

Current graph export counts:

- `events`: 407
- `player_assets`: 229
- `pick_assets`: 137
- `transitions`: 588
- `roster_snapshots`: 40
- `daily_roster_states`: 3652
- `draft_prior_owner_lineages`: 20
- `conditional_pick_families`: 7
- `draft_lottery_results`: 5

Current visualization export counts:

- `lanes`: 172
- `assets`: 366
- `occupancy_intervals`: 1820
- `event_nodes`: 407
- `strand_segments`: 2146
- `event_connectors`: 963
- `conditional_pick_families`: 2
- `draft_lottery_results`: 5

Visualization export commands:

```bash
./.venv/bin/python -m redesign_cli show-visualization-export
./.venv/bin/python -m redesign_cli export-visualization-graph --output-path frontend/src/data/generated/visualization-graph.json
./.venv/bin/python -m redesign_cli inspect-visualization-graph-baseline
```

These are read-only on the data side. The export command only writes the local
artifact file you request.

Audit command:

```bash
.venv/bin/python -m redesign_cli audit-foundation-data
```

This is read-only. Use it after source loads to check source coverage, roster
snapshot shape, draft linkage, aliases, canonical transition counts, and known
remaining data gaps.

NBA.com player movement preview:

```bash
.venv/bin/python -m redesign_cli preview-nba-player-movement
.venv/bin/python -m redesign_cli preview-nba-player-movement --fixture-path tests/foundation/fixtures/nba_player_movement_sample.json
.venv/bin/python -m redesign_cli preview-nba-player-movement --live
.venv/bin/python -m redesign_cli load-nba-player-movement --fixture-path tests/foundation/fixtures/nba_player_movement_sample.json --dry-run
.venv/bin/python -m redesign_cli load-nba-player-movement --live --dry-run
.venv/bin/python -m redesign_cli load-nba-player-movement --fixture-path tests/foundation/fixtures/nba_player_movement_sample.json --execute
.venv/bin/python -m redesign_cli load-nba-player-movement --live --execute
```

This pass prepares dry-run source evidence and canonical guards only. The
preview command reads either a checked-in/local JSON file or the live NBA.com
player movement endpoint, filters Memphis rows by team ID `1610612763`, team
slug `grizzlies`, or Memphis text fallback, and reports endpoint/source
metadata, row counts, date range, transaction type counts, and sample rows.

The guarded `load-nba-player-movement` command stays read-only by default and
only writes when `--execute` is supplied. The dry-run path builds deterministic
`foundation.source_record` and `foundation.source_event` candidates with
`writes_to_database=false`. The execute path upserts the same deterministic rows
into `foundation.source_record` and `foundation.source_event`. Every NBA
movement source event is marked with
`normalized_payload.corroboration_only=true` and
`normalized_payload.canonical_exclusion_reason=nba_player_movement_requires_reconciliation`,
and canonical/derived graph builders ignore those rows by default. The
normalized NBA transaction type is loader compatibility only, not reconciliation
truth. Trade rows now carry Memphis-perspective `player_names_in` and
`player_names_out` derived from NBA.com descriptions, and missing player names
fall back to description parsing before slug inference.

As of 2026-05-17, the live NBA.com preview/dry-run checkpoint reported:

- `9467` total endpoint rows
- `455` Memphis-filtered rows
- date range `2015-07-09` through `2026-04-10`
- transaction types `Signing=184`, `Trade=141`, `Waive=127`,
  `ContractConverted=2`, `AwardOnWaivers=1`
- dry-run candidates `source_record=1`, `source_event=455`

The earlier dry-run graph baseline remained unchanged at that checkpoint, which
is why the NBA.com load could be approved safely before any BRef repair pass.
The current live baseline after the pick backlog closeout is:

- canonical counts `canonical_event=407`, `canonical_event_member=420`,
  `event_asset_transition=568`
- graph export counts `events=407`, `player_assets=229`, `pick_assets=137`,
  `transitions=588`, `roster_snapshots=40`, `daily_roster_states=3652`,
  `draft_prior_owner_lineages=20`, `conditional_pick_families=7`,
  `draft_lottery_results=5`
- graph export checksum
  `0f8d8cb5a30fb853ad91b2556b4539a4fdc22e1db1a28dbb8487984c1646e737`
- visualization export checksum
  `b5792a92d2282550585c154b9cdf85f0674cc4b64c90262921141a6dae616f88`

The live audit now reports loaded source systems `basketball_reference`,
`curated_fixture`, `nba_official`, `nba_player_movement`, and `team_official`,
confirming that the system-level source-coverage gap is closed and the active
corroboration surfaces are all present in the live audit path.

Official roster checkpoint validation commands:

```bash
.venv/bin/python -m redesign_cli preview-roster-snapshot-validation --team-code MEM
.venv/bin/python -m redesign_cli load-roster-snapshot-validation --team-code MEM
```

The validation pass reads the existing `foundation.roster_snapshot` and
`foundation.roster_snapshot_player` rows, compares each checkpoint player set to
loaded official season roster-reference source records, and writes durable
results into `foundation.roster_snapshot_validation`. The validation contract is
truthful by design:

- `source_missing`: no official season roster reference was loaded for that
  season
- `season_reference_backed`: every checkpoint player matched the loaded season
  roster reference
- `season_reference_incomplete`: an official season roster reference exists, but
  not every checkpoint player matched it

This validates season membership only. It does not claim exact day-of-checkpoint
official occupancy.

Current live roster-checkpoint validation state after the composite closeout:

- `roster_snapshot_validation`: `40`
- validation status counts: `season_reference_backed=40`,
  `season_reference_incomplete=0`, `source_missing=0`
- `validated_reference_sources=10`
- live graph checksum still
  `edf5b4a2825b42ec4db14ac08c906cdda5280e5e8cc4935a37d1644ac59ff409`

The checkpoint-depth closeout now uses a broader checked-in official season
composite fixture:

- fixture path:
  [`configs/data/memphis_official_roster_reference_sources_v1.json`](../../configs/data/memphis_official_roster_reference_sources_v1.json)
- residue ledger:
  [`docs/foundation/official-roster-checkpoints/residue-evidence-ledger.yaml`](official-roster-checkpoints/residue-evidence-ledger.yaml)
- loaded `10` `curated_fixture` `official_roster_reference` source records
- reran `load-roster-snapshot-validation --team-code MEM`
- the live audit now reports full season-reference backing across all 40
  checkpoints
- the fixture rows are explicitly season-membership composites normalized toward
  checkpoint reconciliation; they do not claim exact day-of-checkpoint official
  occupancy

Residual limitation:

- the current closeout proves season-reference backing only; it does not create
  exact day-of-checkpoint official occupancy truth

Official-release preview and guarded load:

```bash
.venv/bin/python -m redesign_cli preview-official-release-sources
.venv/bin/python -m redesign_cli preview-official-release-sources --fetch-live
.venv/bin/python -m redesign_cli load-official-release-sources --dry-run
.venv/bin/python -m redesign_cli load-official-release-sources --execute
.venv/bin/python -m redesign_cli load-official-release-sources --fetch-live --execute
```

The starter fixture lives at
[`configs/data/memphis_official_release_sources_seed_v1.json`](../../configs/data/memphis_official_release_sources_seed_v1.json).
It seeds curated official NBA.com and Memphis team-release evidence into
`foundation.source_record` and `foundation.source_event` without affecting
canonical derivation. `--fetch-live` is optional and enriches `raw_payload`
metadata from the live article HTML before write; the default fixture-only mode
still preserves source URLs, titles, timestamps, and curated article excerpts.

The current expanded official-source load writes:

- `43` official `source_record` rows
- `70` official `source_event` rows
- loaded official source systems `nba_official` and `team_official`
- live HTML metadata is now sanitized for NUL bytes before persistence

Current corroboration summary after the recognized-provider contract closeout:

- `meets_minimum=404`
- `out_of_scope=3`
- `bref_only=0`
- `missing_required_evidence=0`
- `recognized_provider_not_loaded=0`
- `events_with_missing_supplemental_roles=368`
- `by_missing_supplemental_role`: `official_confirmation=299`,
  `structured_player_movement=69`
- canonical/graph truth remains unchanged at `canonical_event=407`,
  `canonical_event_member=420`, `event_asset_transition=568`, while the graph
  export checksum now reflects the additive surfaces at
  `edf5b4a2825b42ec4db14ac08c906cdda5280e5e8cc4935a37d1644ac59ff409`

The recognized-provider closeout did not add new source rows. It changed the
audit contract so minimum truthful corroboration is separate from supplemental
corroboration depth:

- player movement now meets minimum with `chronology_spine` plus one loaded
  corroborating movement surface
- draft/pick detail now meets minimum with loaded `secondary_pick_detail`
- missing official confirmation or missing structured movement remains visible
  as supplemental residue in the audit output rather than as an open
  minimum-truth gap

The final recent 2023 unresolved `bref_only` residue is now closed:

- `2023-08-31` Gregory Jackson signing now lands as `meets_minimum`
- `2023-10-16` Timmy Allen signing now lands as `meets_minimum`
- `2023-10-16` Jason Preston signing now lands as `meets_minimum`
- `2023-10-16` Matthew Hurt waiver now lands as `meets_minimum`

The October 16 curated transaction-cluster row also truthfully carries the
paired `Mychal Mulder` waiver event even though it was not one of the four
required closeout targets.

Two-way and contract-semantics closeout commands:

```bash
.venv/bin/python -m redesign_cli preview-two-way-status --team-code MEM
.venv/bin/python -m redesign_cli load-two-way-status --team-code MEM --dry-run
.venv/bin/python -m redesign_cli load-two-way-status --team-code MEM
.venv/bin/python -m redesign_cli inspect-contract-semantics
```

Current live closeout results:

- `two_way_status.status=complete_historical_coverage`
- two-way fixture rows `=19`
- loadable two-way fixture rows `=19`
- non-loadable two-way fixture rows `=0`
- loaded two-way snapshot-player rows `=48`
- `contract_semantics.status=complete`
- contract-semantic candidate events `=267`
- structured contract-semantic events `=267`
- missing required structured contract-semantic fields `=0`
- explicit contract-detail rows `=112`
- implicit-only contract-detail rows `=155`

The current closeout still keeps richer contract semantics additive:

- graph-facing canonical event types remain `trade`, `draft`, `signing`,
  and `waiver`
- structured contract semantics live on loaded
  `foundation.source_event.normalized_payload`
- daily roster state now reflects the reloaded contract-status truth surface
  after the two-way refresh

Current live audit documented limitations/context after the closeout:

- source-backed conditional future-pick fallback rows now persist in the
  obligation ledger and export as bounded conditional-family data while staying
  out of concrete snapshot ownership

Daily roster state and draft prior-owner lineage commands:

```bash
.venv/bin/python -m redesign_cli bootstrap-foundation-daily-roster-and-prior-owner
.venv/bin/python -m redesign_cli preview-daily-roster-state
.venv/bin/python -m redesign_cli load-daily-roster-state --dry-run
.venv/bin/python -m redesign_cli load-daily-roster-state
.venv/bin/python -m redesign_cli preview-draft-prior-owner-lineage
.venv/bin/python -m redesign_cli preview-draft-prior-owner-replay-proof
.venv/bin/python -m redesign_cli load-draft-prior-owner-lineage --dry-run
.venv/bin/python -m redesign_cli load-draft-prior-owner-lineage
```

Current live results after the closeout:

- `daily_roster_state=3652`
- `daily_roster_state_player=61979`
- daily coverage span `2016-07-01` through `2026-06-30`
- daily coverage complete with `internal_missing_days=0`
- graph-facing daily player surface capped at `18` with up to `3` two-way rows
- `draft_prior_owner_lineage=20`
- `draft.selections_missing_prior_owner=0`
- the live audit no longer reports daily roster state generation or draft-night
  prior ownership lineage as open gaps

Implementation notes:

- daily roster rows are anchored on the validated quarterly checkpoint
  snapshots and carry forward between anchors using loaded same-day events
- the daily surface is intentionally bounded to the graph-facing 18-player slot
  surface because full fringe contract semantics remain a separate backlog item
- draft prior-owner lineage now resolves from selection-day inventory and exact
  source-event derivation without active override reliance for the Memphis span

Locator choices used for the closeout:

- Gregory Jackson II signing: `https://gleague.nba.com/news/memphis-grizzlies-sign-gg-jackson-ii-to-two-way-contract`
- October 16 transaction cluster fallback: `https://www.nba.com/players/transactions`
- Secondary confirmation used for the October 16 cluster text: `https://www.hoopsrumors.com/2023/10/grizzlies-sign-jason-preston-timmy-allen.html`

The bounded 2022 preseason/camp older-chronology cluster is now also closed
from a `bref_only` perspective:

- `2022-09-23` Jacob Gilyard signing
- `2022-09-23` Justin Bean signing
- `2022-10-10` Matthew Hurt signing
- `2022-10-10` Sean McDermott signing
- `2022-10-13` E.J. Onu signing
- `2022-10-13` Romeo Weems signing
- `2022-10-13` Matthew Hurt waiver
- `2022-10-14` Dakota Mathias signing

These 8 canonical events reconcile with `conflict_status=no_conflict_detected`.
Under the current corroboration contract, they now count as `meets_minimum`
because loaded official confirmation satisfies the minimum player-movement
support path alongside the chronology spine; the missing structured movement
surface remains visible only as supplemental residue in the audit output.

Locator choices used for the 2022 closeout:

- Grizzlies playoff media guide transaction log:
  `https://s3.grizzliesapp.com/assets/media_guides/MG_22-23_Playoffs_Media_Guide.pdf`
- Dakota Mathias official release:
  `https://www.nba.com/grizzlies/news/memphis-grizzlies-sign-dakota-mathias`

Graph baseline checkpoint output:

```bash
.venv/bin/python -m redesign_cli inspect-foundation-graph-baseline
```

This is read-only. It reports current canonical table counts, graph export
counts, and a graph export checksum for review around any future live load.

Draft-resolution preview:

```bash
.venv/bin/python -m redesign_cli preview-draft-pick-resolution --team-code MEM
```

This is read-only. It reports whether `draft_selection` rows are already linked
to `pick` rows, have conservative candidate matches, are ambiguous, or cannot be
matched because owned/future pick inventory rows are missing.

Curated draft-slot preview:

```bash
.venv/bin/python -m redesign_cli preview-curated-draft-pick-resolution --team-code MEM
```

This is read-only. It compares
[`configs/data/memphis_draft_pick_resolution_2016_2025.json`](../../configs/data/memphis_draft_pick_resolution_2016_2025.json)
against live `draft_selection` rows and reports whether a later write path would
create slot-based `pick` rows, link existing rows, or block because source rows
do not match.

Guarded draft-resolution load:

```bash
.venv/bin/python -m redesign_cli load-curated-draft-pick-resolution --team-code MEM --dry-run
.venv/bin/python -m redesign_cli load-curated-draft-pick-resolution --team-code MEM
```

The non-dry-run command writes only after the curated preview has zero blocked
rows. It creates slot-based `pick` and `asset` rows, links
`draft_selection.pick_id`, and records provenance in
`foundation.draft_pick_resolution`.

Two-way status preview and guarded load:

```bash
.venv/bin/python -m redesign_cli preview-two-way-status --team-code MEM
.venv/bin/python -m redesign_cli load-two-way-status --team-code MEM --dry-run
.venv/bin/python -m redesign_cli load-two-way-status --team-code MEM
```

Run two-way enrichment after `load-roster-snapshots-from-baselines`, because the
snapshot builder rebuilds all snapshot-player rows as standard. The live load is
deterministic within the `seed_v1` fixture coverage: it resets covered Memphis
snapshot-player rows to standard, then applies current high-confidence loadable
intervals. Non-matching intervals are warnings, not inserts.

Draft lottery result preview and guarded load:

```bash
.venv/bin/python -m redesign_cli preview-draft-lottery-results --team-code MEM
.venv/bin/python -m redesign_cli load-draft-lottery-results --team-code MEM --dry-run
.venv/bin/python -m redesign_cli load-draft-lottery-results --team-code MEM
```

The fixture writes Memphis-perspective lottery result rows for 2018, 2019,
2020, 2024, and 2026. Loadable rows require high confidence, source URLs,
source labels, retrieval dates, safe lottery slot values, and explicit
`owner_team_code` / `original_team_code`. The command blocks duplicate fixture
year/team rows and existing DB `(draft_year, team_code)` rows with a different
`lottery_result_id` before any write. The 2020 Memphis-origin row is loaded with
`owner_team_code=BOS` and `original_team_code=MEM`.

Future pick inventory preview and guarded load:

```bash
.venv/bin/python -m redesign_cli preview-pick-inventory-obligations --team-code MEM
.venv/bin/python -m redesign_cli preview-pick-inventory-obligations --team-code MEM --allow-update-id <obligation_id>
.venv/bin/python -m redesign_cli load-pick-inventory-obligations --team-code MEM --dry-run
.venv/bin/python -m redesign_cli load-pick-inventory-obligations --team-code MEM --dry-run --allow-update-id <obligation_id>
.venv/bin/python -m redesign_cli load-pick-inventory-obligations --team-code MEM
.venv/bin/python -m redesign_cli load-pick-inventory-snapshots --team-code MEM --dry-run --max-draft-year 2032
.venv/bin/python -m redesign_cli load-pick-inventory-snapshots --team-code MEM --max-draft-year 2032
```

The obligation load writes only source-backed loadable fixture rows. Use
`--allow-update-id` only for an explicitly reviewed source-backed correction to
one existing obligation row; without that flag, conflicting existing rows remain
blocked. The snapshot load projects default Memphis own picks plus dated
obligation rows and replaces covered `roster_snapshot_pick` rows to avoid stale
projection state.

Resolved in this pass:

- `Kenny Lofton Jr` source text now resolves to `Kenneth Lofton Jr.`
- full-span Basketball-Reference transaction pages now feed the source event layer
- full-span Basketball-Reference roster pages now feed roster baselines
- Memphis Basketball-Reference draft selections now feed `draft_selection`
- curated Memphis draft-slot rows now link all `draft_selection` rows to
  slot-based `pick` assets with provenance in `draft_pick_resolution`
- roster checkpoint rows now export instead of leaving `roster_snapshots` empty
- roster checkpoint player rows are now capped, date-aware reconstructions from
  Basketball-Reference season roster pages plus loaded transaction events
- `draft_pick_resolution` rows now emit graph-facing `pick_to_player`
  transitions and synthetic draft events for the frontend export
- `seed_v1` two-way status intervals can now populate
  `roster_snapshot_player.is_two_way` for matching Memphis checkpoint rows
- `seed_v1` draft lottery result rows can populate contextual
  Memphis-perspective lottery outcomes for 2018, 2019, 2020, 2024, and 2026
  after clean preview/dry-run. The current live database has 5 loaded lottery
  rows, all with owner/original-team semantics.
- `seed_v1` future-pick obligation rows can populate
  `pick_inventory_obligation` and projected `roster_snapshot_pick` rows after
  clean preview/dry-run. The current live database has 28 loaded obligation rows
  (26 projectable plus 2 bounded non-projectable fallback rows) and 980
  projected snapshot-pick rows.
- the ORL 2028 first acquired in the Bane trade and sent out in the Cedric
  Coward draft trade now resolves to `owner_team_code=POR` instead of
  `UNKNOWN`, based on NBA.com and RealGM source checks
- `audit-foundation-data` now reports currentness as verified through a dated
  source review, fixture-level fallback documentation context, source coverage,
  and deferred draft-night ownership-lineage limits
- curated official NBA.com/team-release source rows can now load into
  `foundation.source_record` and `foundation.source_event` through
  `load-official-release-sources`, and the live database now includes a first
  starter batch of 4 official records / 6 official events
- a generated `curated_fixture` draft-pick-detail source path can now load one
  corroboration-only source record plus 20 draft source events derived from the
  loaded Memphis `draft_selection` truth surface, which closes the live
  `missing_required_evidence` draft bucket

Documented limitations and remaining backlog:

- Source coverage is no longer Basketball-Reference-only. The live database now
  includes loaded `nba_player_movement`, `nba_official`, `team_official`, and
  `curated_fixture` corroboration systems, and the audit's
  `source_coverage_report` gap remains cleared.
- Minimum event-level corroboration is now complete for in-scope events. The
  latest live audit reports `known_gaps=[]`, `meets_minimum=404`,
  `bref_only=0`, `missing_required_evidence=0`,
  `recognized_provider_not_loaded=0`, and `out_of_scope=3`. Supplemental
  corroboration depth still trails at
  `events_with_missing_supplemental_roles=368`.
- Draft lottery rows now emit through the additive `draft_lottery_results`
  export surface with durable pick linkage, while staying outside graph
  events/transitions.
- Future pick inventory is now loaded at `28` source-backed obligation rows:
  `26` projectable rows plus `2` bounded non-projectable fallback rows.
  The ledger includes `8` historical selection-day replay rows used by the
  draft prior-owner proof surface. The reset-era replay contract is closed for
  realized Memphis-visible states, even though the fixture still stops short of
  a full hypothetical branch engine.
- The Lakers 2027 and Orlando 2029 fallback-second cases now persist as
  non-projectable obligation rows and export as bounded conditional-family
  surfaces instead of remaining fixture-only documentation.
- Draft-night selected-slot resolution and prior-owner lineage are complete for
  loaded Memphis draft selections. The live replay proof reports
  `replay_coverage.status=complete` with zero remaining override reliance.
