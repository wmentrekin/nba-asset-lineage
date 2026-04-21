# Provenance And Build Versioning Contract

## Purpose

Define the minimum write contract for provenance and rebuild versioning before
implementation begins.

The planning set already says the system must be deterministic and auditable.
This document makes that concrete.

## Status

This is a minimum contract for implementation, not a complete long-term audit
design.

## Provenance Scope

The following canonical object families require provenance rows in v1:

- canonical events
- graph asset identities
- player identities where identity resolution was non-trivial
- pick assets
- asset state rows that drive rendering or lineage interpretation

Presentation outputs do not need row-level provenance tables in v1 as long as
they are reproducible from canonical data plus build version metadata.

## Provenance Granularity

V1 provenance should be row-level, not field-level.

That means a provenance row explains why a canonical row exists or was chosen.

It does not need to justify every individual scalar field separately.

Reason:

- row-level provenance is sufficient to start implementation
- field-level provenance would slow the project materially

## Required Provenance Inputs

A provenance row may point to:

- `source_record_id`
- `claim_id`
- `override_id`
- builder fallback reason

At least one of those must be present.

## Required Provenance Roles

### Event Rows

Required roles:

- `event_date_support`
- `event_type_support`
- `event_cluster_support`

Conditional roles:

- `event_order_override`
- `event_order_source_fallback`
- `event_order_deterministic_fallback`

### Graph Asset Rows

Required roles:

- `asset_identity_support`

Conditional roles:

- `player_identity_resolution_support`
- `pick_identity_support`

### Asset State Rows

Required roles:

- `asset_state_support`

Conditional roles:

- `buyout_metadata_support`
- `lane_eligibility_support`
- `drafted_player_linkage_support`

## Override Encoding

If an override materially changes a canonical result, provenance must contain a
row referencing that `override_id`.

This applies to:

- event ordering
- event merge/split
- identity correction
- source exclusion
- pick metadata correction

Override records should be treated as versioned curation inputs. They may be
loaded from repository-tracked YAML or JSON bundles, but the canonical builders
should not bury individual override decisions inside transformation code. This
keeps curated judgment reviewable, reproducible, and linkable from provenance.

## Fallback Encoding

If no override was used and the builder had to apply a deterministic fallback,
that must also be recorded in provenance.

Examples:

- source order chosen as fallback
- stable sort key chosen because source sequence was unavailable

This is important because "deterministic" is not the same as "self-evident."

## Build Versioning

The system should record version metadata for:

- evidence build
- canonical build
- presentation build

## Minimum Build Metadata

### Evidence Build

Recommended fields:

- `evidence_build_id`
- `built_at`
- `builder_version`
- `source_record_count`
- `claim_count`
- `override_count`
- `notes`

### Canonical Build

Recommended fields:

- `canonical_build_id`
- `built_at`
- `builder_version`
- `evidence_build_id`
- `override_snapshot_hash`
- `notes`

### Presentation Build

Recommended fields:

- `presentation_build_id`
- `built_at`
- `builder_version`
- `canonical_build_id`
- `notes`

## Rebuild Policy

V1 recommendation:

- evidence rows are append-oriented
- canonical rows may be rebuilt in place during development
- each canonical rebuild should still record a new build metadata row
- presentation exports should be tied to one canonical build ID

This gives enough reproducibility without requiring immutable snapshot storage
for every row in the first implementation.

## Comparison Policy

The system should make it possible to compare builds by:

- row counts
- build metadata
- exported snapshots
- targeted validation queries

V1 does not need a full diff engine, but it should not make diffing impossible.

## Recommendation

This contract should be treated as required before canonical builders are
implemented.
