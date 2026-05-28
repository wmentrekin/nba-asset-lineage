# Config Data

This directory is reserved for active reset-era tracked configuration and input
files.

At the moment the prior override/editorial/headshot bundles have been archived
to `legacy/configs/data/` while the new foundation schema and source
requirements are being redefined.

When reset-era data bundles are introduced here, they should support the
minimum lineage output first:

- source definitions
- ingest mappings
- deterministic lineage/reference data

Current active bundles:

- `memphis_draft_pick_resolution_2016_2025.json`
  - curated Memphis draft-slot selections from 2016 through 2025
  - used by the read-only `preview-curated-draft-pick-resolution` command
  - asserts selected-player/draft-slot truth, not complete pick-ownership
    history
- `memphis_future_pick_obligations_2016_2026.json`
  - `seed_v1` source-backed Memphis future-pick obligation rows for the
    reset-era pick inventory workbench
  - used by the read-only `preview-pick-inventory-obligations` validation
    command and the `preview-pick-inventory-snapshots` projection command
  - stores explicit perspective, owner, and original team codes plus source
    URLs, labels, retrieval timestamps, confidence, and source event links for
    loadable rows
  - includes non-loadable documentation rows for conditional fallbacks that
    should not be written until the projection semantics are stable
  - not yet a complete 2016-2026 historical obligation ledger
- `memphis_two_way_status_2017_2026.json`
  - curated source-backed Memphis two-way contract intervals across the
    in-scope span
  - used by `preview-two-way-status` and guarded `load-two-way-status`
  - updates existing `roster_snapshot_player` rows only; it does not create
    players, aliases, snapshots, or snapshot-player rows
  - currently closes the Memphis two-way historical coverage gap in the live
    audit
- `memphis_draft_lottery_results_2016_2026.json`
  - `seed_v1` curated high-confidence Memphis-perspective draft lottery
    outcomes for 2018, 2019, 2020, 2024, and 2026
  - used by `preview-draft-lottery-results` and guarded
    `load-draft-lottery-results`
  - includes source URLs, labels, retrieval dates, confidence, and notes for
    loadable rows
  - uses `team_code` as the Memphis perspective scope and stores explicit
    `owner_team_code` / `original_team_code`, including the 2020
    Memphis-origin pick owned by Boston
  - contextual metadata only; it is not consumed by the base graph export
