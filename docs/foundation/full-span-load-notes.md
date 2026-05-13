# Full-Span Load Notes

Last verified live load scope:

- team: Memphis Grizzlies
- transaction seasons: 2016-17 through 2025-26
- draft years: 2016 through 2025
- source span in export: 2016-06-23 through 2026-04-10

Current live `foundation` counts after the full-span rebuild plus contextual
seed enrichments:

- `source_record`: 588
- `source_event`: 401
- `player`: 227
- `player_alias`: 1
- `pick`: 82
- `asset`: 309
- `roster_baseline_player`: 222
- `roster_snapshot`: 40
- `roster_snapshot_player`: 644
- `roster_snapshot_pick`: 0
- `draft_selection`: 20
- `draft_pick_resolution`: 20
- `draft_lottery_result`: 4
- `canonical_event`: 388
- `canonical_event_member`: 401
- `event_asset_transition`: 528

Current graph export counts:

- `events`: 408
- `player_assets`: 227
- `pick_assets`: 82
- `transitions`: 548
- `roster_snapshots`: 40

Audit command:

```bash
.venv/bin/python -m redesign_cli audit-foundation-data
```

This is read-only. Use it after source loads to check source coverage, roster
snapshot shape, draft linkage, aliases, canonical transition counts, and known
remaining data gaps.

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

The fixture writes only Memphis-owned lottery result rows for 2018, 2019, 2024,
and 2026. Loadable rows require high confidence, source URLs, source labels,
retrieval dates, and safe lottery slot values. The command blocks duplicate
fixture year/team rows and existing DB `(draft_year, team_code)` rows with a
different `lottery_result_id` before any write. The 2020 Boston-from-Memphis
result is documented as `loadable=false` and is not written because the current
table cannot distinguish owner team from original team.

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
- `seed_v1` draft lottery result rows can populate contextual Memphis-owned
  lottery outcomes for 2018, 2019, 2024, and 2026 after clean preview/dry-run.
  The current live database has 4 loaded lottery rows.

Known gaps:

- `roster_snapshot_pick` is still empty because current pick inventory snapshots
  are not sourced yet.
- Draft lottery rows are contextual seed coverage only and are not consumed by
  the base graph. The audit clears only the empty-table gap and preserves a
  caveat that 2020 Boston-from-Memphis remains excluded until owner and
  original-team semantics are modeled separately.
- Two-way status now has a curated seed loader, but nonzero two-way rows only
  prove loaded seed coverage. The fixture is not complete historical coverage.
