# Full-Span Load Notes

Last verified live load scope:

- team: Memphis Grizzlies
- transaction seasons: 2016-17 through 2025-26
- draft years: 2016 through 2025
- source span in export: 2016-06-23 through 2026-04-10

Current live `foundation` counts after the full-span rebuild:

- `source_record`: 588
- `source_event`: 401
- `player`: 227
- `player_alias`: 1
- `pick`: 82
- `asset`: 309
- `roster_baseline_player`: 222
- `roster_snapshot`: 40
- `roster_snapshot_player`: 888
- `roster_snapshot_pick`: 0
- `draft_selection`: 20
- `draft_pick_resolution`: 20
- `draft_lottery_result`: 0
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

Resolved in this pass:

- `Kenny Lofton Jr` source text now resolves to `Kenneth Lofton Jr.`
- full-span Basketball-Reference transaction pages now feed the source event layer
- full-span Basketball-Reference roster pages now feed roster baselines
- Memphis Basketball-Reference draft selections now feed `draft_selection`
- curated Memphis draft-slot rows now link all `draft_selection` rows to
  slot-based `pick` assets with provenance in `draft_pick_resolution`
- roster checkpoint rows now export instead of leaving `roster_snapshots` empty
- `draft_pick_resolution` rows now emit graph-facing `pick_to_player`
  transitions and synthetic draft events for the frontend export

Known gaps:

- Basketball-Reference roster pages are season roster references, not exact
  checkpoint snapshots.
- `roster_snapshot_pick` is still empty because current pick inventory snapshots
  are not sourced yet.
- `draft_lottery_result` is still empty; lottery data is contextual and not
  required for the base graph.
- Two-way versus standard contract status is modeled but not reliably sourced
  yet.
