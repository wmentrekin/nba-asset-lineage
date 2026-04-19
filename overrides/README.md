# Curated Overrides

This directory contains versioned curation inputs for the redesign pipeline.

Override files are not raw source evidence and they are not transformation
logic. They are explicit human-reviewed decisions used when source evidence is
ambiguous or mechanically split in a way that would produce the wrong canonical
result.

The redesign loader reads `*.json`, `*.yaml`, and `*.yml` files under this
directory by default:

```bash
uv --cache-dir /tmp/uv-cache run python -m redesign_cli load-overrides --overrides-path overrides
```

## Current Bundle

`stage2_event_merge_overrides.yaml` contains Stage 2 canonical event merge
overrides for Memphis transaction rows that represent one compound event but
arrive from Spotrac as multiple source clusters.

Each active merge override should include:

- a stable `override_id`
- `override_type: merge_event_cluster`
- `target_type: event_cluster`
- a `target_key`
- `payload.source_cluster_keys`
- `payload.target_cluster_key`
- a human-readable `reason`
- `authored_by`, `authored_at`, and `is_active`

When a merge override changes canonical event output, Stage 2 must record
`canonical.event_provenance` with `provenance_role = event_merge_support`.

## Operational Rule

Do not put scratch files in this directory unless they are valid override
bundles that should be loaded by the pipeline.
