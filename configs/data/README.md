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
