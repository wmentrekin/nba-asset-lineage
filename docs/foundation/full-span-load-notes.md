# Full-Span Load Notes

Last verified live load scope:

- team: Memphis Grizzlies
- transaction seasons: 2016-17 through 2025-26
- draft years: 2016 through 2025
- source span in export: 2016-06-23 through 2026-04-10
- currentness source review: no later public Memphis roster event verified
  through 2026-05-14

Current live `foundation` counts after the full-span rebuild plus contextual
seed enrichments plus the expanded official-source corroboration load:

- `source_record`: 622
- `source_event`: 922
- `player`: 229
- `player_alias`: 1
- `pick`: 128
- `asset`: 357
- `roster_baseline_player`: 222
- `roster_snapshot`: 40
- `roster_snapshot_player`: 636
- `roster_snapshot_pick`: 980
- `draft_selection`: 20
- `draft_pick_resolution`: 20
- `draft_lottery_result`: 5
- `canonical_event`: 408
- `canonical_event_member`: 421
- `event_asset_transition`: 569

Current graph export counts:

- `events`: 408
- `player_assets`: 229
- `pick_assets`: 128
- `transitions`: 589
- `roster_snapshots`: 40

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
The current live baseline after the later BRef corroboration rebuild is:

- canonical counts `canonical_event=408`, `canonical_event_member=421`,
  `event_asset_transition=569`
- graph export counts `events=408`, `player_assets=229`, `pick_assets=128`,
  `transitions=589`, `roster_snapshots=40`
- graph export checksum
  `ffa34c46acbb824706f9745169430e6792c6f2e838d2a8b41adff3c873db031a`

The live audit now reports loaded source systems `basketball_reference`,
`nba_official`, `nba_player_movement`, and `team_official`, confirming that the
system-level source-coverage gap is closed and the official-source path is now
live.

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

- `33` official `source_record` rows
- `46` official `source_event` rows
- loaded official source systems `nba_official` and `team_official`

Current corroboration summary after the expanded official-source load:

- `bref_only=67`
- `meets_minimum=25`
- `recognized_provider_not_loaded=278`
- `missing_required_evidence=38`
- `conflict_suspected=0`

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
  clean preview/dry-run. The current live database has 19 loaded obligation rows
  and 980 projected snapshot-pick rows.
- the ORL 2028 first acquired in the Bane trade and sent out in the Cedric
  Coward draft trade now resolves to `owner_team_code=POR` instead of
  `UNKNOWN`, based on NBA.com and RealGM source checks
- `audit-foundation-data` now reports currentness as verified through a dated
  source review, fixture-only fallback documentation rows, source coverage, and
  deferred draft-night ownership-lineage limits
- curated official NBA.com/team-release source rows can now load into
  `foundation.source_record` and `foundation.source_event` through
  `load-official-release-sources`, and the live database now includes a first
  starter batch of 4 official records / 6 official events

Known gaps:

- Source coverage is no longer Basketball-Reference-only. The live database now
  includes one loaded `nba_player_movement` source record and 455 loaded
  corroboration-only NBA.com movement source events, and the audit's
  `source_coverage_report` gap is cleared.
- Event-level player-movement corroboration remains partial after the NBA.com
  load, follow-on audit reconciliation passes, and first official-source load:
  the latest audit reports 276 canonical events with `no_conflict_detected`
  corroboration, 94 events still `bref_only`, 272
  `recognized_provider_not_loaded`, 4 `meets_minimum`, and 9 trade events
  surfaced as `conflict_suspected`.
- Draft lottery rows are contextual seed coverage only and are not consumed by
  the base graph. The audit clears only the empty-table gap and preserves a
  caveat that lottery rows remain contextual seed coverage.
- Two-way status now has a curated seed loader, but nonzero two-way rows only
  prove loaded seed coverage. The fixture is not complete historical coverage.
- Future pick inventory is now non-empty and source-backed, but the fixture is
  still a current-state-focused seed ledger rather than a complete historical
  replay of every obligation branch.
- Two fallback pick facts are still fixture documentation only: the Lakers 2027
  second fallback and Orlando 2029 second fallback remain non-loadable until
  conditional branch semantics can prevent simultaneous primary/fallback
  projection.
- Draft-night selected-slot resolution is complete for loaded draft selections,
  but prior pick ownership lineage remains deferred.
