# Curated Overrides

This directory contains versioned curation inputs for the redesign pipeline.

Override files are not raw source evidence and they are not transformation
logic. They are explicit human-reviewed decisions used when source evidence is
ambiguous or mechanically split in a way that would produce the wrong canonical
result.

The redesign loader reads `*.json`, `*.yaml`, and `*.yml` files under
`configs/data/` by default:

```bash
uv --cache-dir /tmp/uv-cache run python -m redesign_cli load-overrides
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

`stage7_editorial_overlays.yaml` contains the tracked Stage 7 editorial overlay
seed bundle for Memphis-only narrative context. It is separate from canonical
lineage truth and can be loaded into the `editorial` schema with:

```bash
uv --cache-dir /tmp/uv-cache run python -m redesign_cli load-editorial-overlays
```

`stage8_headshot_manifest.yaml` is the tracked Stage 8 fixture manifest for
optional repo-local identity-marker images. It maps stable canonical `asset_id`
values to static files under `frontend/public/`, for example
`headshots/example-player.svg`. Layout export resolves only paths that exist
locally; missing or absent mappings are coerced to text-only markers.

## Operational Rule

Do not put scratch files in this directory unless they are valid override
bundles that should be loaded by the pipeline.
