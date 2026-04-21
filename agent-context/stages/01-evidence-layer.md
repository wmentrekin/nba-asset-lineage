# Stage 01 Evidence Layer Spec

## Purpose

Define the first implementation stage for the redesigned system:

- evidence schema bootstrap
- raw source capture
- normalized claims
- manual overrides

This document should be specific enough for an implementation agent to begin
building Stage 1.

## Stage Objective

Create the new evidence foundation without depending on canonical lineage logic.

At the end of this stage, the repo should be able to:

- ingest source data into `evidence.source_records`
- derive normalized claims into `evidence.normalized_claims`
- persist manual overrides separately
- inspect and validate evidence independently of the old Bronze/Silver pipeline

## In Scope

- new SQL bootstrap for `evidence.*`
- Python modules for evidence ingestion and normalization
- ingestion of initial source inputs
- local override format and override loading
- minimal tests and validation utilities

## Out Of Scope

- canonical event generation
- player tenure modeling
- pick lifecycle logic beyond source claims
- frontend exports
- editorial overlays

## Initial Source Scope

Stage 1 should support these initial sources:

1. Spotrac transaction records
2. Spotrac contract records, if useful for player-state evidence
3. `nba_api` draft history rows

These are confirmed initial evidence sources for the redesign.

The purpose is not to model everything yet. The purpose is to establish the new
evidence contract.

## Recommended Directory Shape

Suggested implementation targets:

- `src/evidence/`
- `src/evidence/models.py`
- `src/evidence/ingest.py`
- `src/evidence/normalize.py`
- `src/evidence/overrides.py`
- `src/evidence/validate.py`
- `sql/0001_evidence_bootstrap.sql`
- `tests/evidence/`
- `configs/data/`

## Schema Objects

## `evidence.source_records`

### Responsibility

Store one row per captured raw source record.

### Required Fields

- `source_record_id`
- `source_system`
- `source_type`
- `source_locator`
- `source_url`
- `captured_at`
- `raw_payload`
- `payload_hash`
- `parser_version`
- `created_at`

### Notes

- `payload_hash` should support dedupe and auditability.
- `raw_payload` should preserve the source row or object as faithfully as
  practical.
- `source_locator` should identify the logical fetch location or grouping, such
  as a URL, API endpoint, or import filename.

## `evidence.normalized_claims`

### Responsibility

Store structured claims extracted from raw source records.

### Required Fields

- `claim_id`
- `source_record_id`
- `claim_type`
- `claim_subject_type`
- `claim_subject_key`
- `claim_group_hint`
- `claim_date`
- `source_sequence`
- `claim_payload`
- `confidence_flag`
- `normalizer_version`
- `created_at`

### Notes

- one source record may generate many normalized claims
- claims remain source-attributed and non-canonical
- `source_sequence` is required when the source provides stable row or listing
  order
- `claim_group_hint` should capture builder-useful grouping hints without
  claiming canonical truth
- `normalizer_version` must live on claims, not only on raw records

## `evidence.overrides`

### Responsibility

Store manual corrections and curation separately from raw evidence.

### Required Fields

- `override_id`
- `override_type`
- `target_type`
- `target_key`
- `payload`
- `reason`
- `authored_by`
- `authored_at`
- `is_active`

### Notes

- overrides should be additive and explicit
- overrides should not mutate source records directly

## `evidence.override_links`

### Responsibility

Connect overrides to source records and claims when precise targeting is needed.

### Required Fields

- `override_link_id`
- `override_id`
- `source_record_id`
- `claim_id`

### Notes

- this table is optional in the very first commit if direct targeting by key is
  sufficient
- if omitted initially, the spec should still leave room for it

## Initial Claim Types

Stage 1 does not need every possible claim type. Start with a constrained set.

### Event Claims

- `event_date`
- `event_type`
- `event_description`
- `event_order_hint`
- `transaction_counterparty`

### Player Claims

- `player_identity`
- `player_name`

### Pick Claims

- `pick_identity`
- `pick_origin_team`
- `pick_draft_year`
- `pick_round`
- `pick_protection_metadata`
- `pick_resolution_metadata`

### Contract / Exit Claims

- `contract_metadata`
- `waiver_metadata`
- `buyout_metadata`

## Subject Key Strategy

Stage 1 should define how claims refer to the thing they are about, even before
canonical IDs exist.

Recommended temporary subject key examples:

- event-like key:
  `spotrac_tx::<source_event_ref>`
- player-like key:
  `player_name::<normalized_name>`
- pick-like key:
  `pick::<draft_year>::<origin_team>::<round>`

These are temporary evidence-layer keys, not final canonical IDs.

Upgrade path:

- Stage 2 may map multiple evidence-layer subject keys into one event candidate
  cluster
- later canonical builders must not reuse these temporary keys as final IDs

## Claim Cardinality Guidance

Stage 1 should keep claim cardinality explicit.

Examples:

- one source record may emit one `event_date` claim
- one source record may emit several player-related claims
- one source record may emit both pick metadata and event-description claims

Normalization code should avoid silently overwriting multiple same-type claims
from one source record.

## Override Format

For Stage 1, the simplest workable override approach is file-based structured
data plus DB loading.

Recommended location:

- `configs/data/`

Recommended file format:

- YAML or JSON

Recommended initial override categories:

- event ordering override
- source exclusion override
- event merge hint
- pick metadata correction
- player identity correction

Recommended minimum payload shapes:

- `event ordering override`
  - `event_cluster_key`
  - `event_date`
  - `event_order`
- `event merge hint`
  - `source_record_ids`
  - `target_cluster_key`
- `source exclusion override`
  - `source_record_id`
  - `reason_code`

## Ingestion Responsibilities

Stage 1 ingestion code should do the following:

1. fetch or load raw source rows
2. write `evidence.source_records`
3. normalize each source row into one or more `evidence.normalized_claims`
4. load structured overrides into `evidence.overrides`
5. provide basic validation/reporting output

It should not:

- construct canonical events
- merge multiple source claims into one canonical truth object

## Normalization Responsibilities

Stage 1 normalization should focus on extraction, not interpretation.

Good examples:

- extract a date claim from source text
- extract a player name
- extract draft year and round
- extract buyout text into metadata
- carry source sequence into normalized claims where available
- emit grouping hints for likely event clustering

Bad examples for Stage 1:

- deciding the final canonical event order
- deciding whether two source rows belong to one canonical trade event

## Determinism Rules

Stage 1 must be deterministic.

That means:

- identical source inputs produce identical source-record dedupe behavior
- identical parsing logic produces identical claim outputs
- identical override files produce identical override rows

## Validation And Tests

Stage 1 should ship with lightweight but real validation.

### Minimum Test Coverage

- raw source record ingestion
- payload hash stability
- one-to-many claim generation from one source record
- override loading
- basic dedupe expectations

### Recommended Fixture Types

- one Spotrac transaction example
- one Spotrac contract example
- one `nba_api` draft example
- one override example for same-day ordering or pick metadata correction

### Suggested Validation Outputs

- number of source records ingested
- number of claims emitted by type
- number of overrides loaded
- duplicate source records skipped

## Stage 1 Deliverable Checklist

The stage is complete when the repo has:

- a new evidence bootstrap SQL file
- evidence ingestion code
- evidence normalization code
- override loading support
- tests for core evidence behaviors
- at least one runnable command for loading evidence

## Suggested Commands

Examples only; exact naming can change:

- `mise run redesign_evidence_bootstrap`
- `mise run redesign_evidence_ingest`
- `mise run redesign_evidence_validate`

## Recommended First Implementation Task Sequence

The best order inside Stage 1 is:

1. create repo structure and SQL bootstrap
2. implement `source_records` ingestion
3. implement `normalized_claims` emission
4. implement override loading
5. add tests and validation commands

## Risks

### Risk 1: Over-Normalizing Too Early

If Stage 1 tries to decide canonical truth, it will blur the evidence/canonical
boundary.

Mitigation:

- keep normalized claims source-attributed and non-canonical

### Risk 2: Weak Subject Keys

If temporary claim subject keys are too unstable, later reconciliation will be
hard.

Mitigation:

- define subject-key conventions explicitly
- keep them simple and auditable

### Risk 3: Overrides Becoming Ad Hoc

If override structure is vague, it will become hard to audit.

Mitigation:

- define override types from the start
- require `reason` for every override

## Handoff To Stage 2

Stage 2 should consume Stage 1 outputs to build:

- canonical events
- event provenance
- explicit same-day ordering
- compound transaction grouping

That means Stage 1 should optimize for giving Stage 2 good evidence, not for
solving canonicalization early.

## Recommendation

This spec is sufficient to begin implementation of Stage 1.

The next planning artifact after Stage 1 implementation begins should be:

- `agent-context/stages/02-canonical-events.md`

But that does not need to be written before starting Stage 1 code.
