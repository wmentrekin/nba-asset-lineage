# Implementation Stage Plan

## Purpose

Define the staged execution plan for replacing the current pipeline with the new
evidence/canonical/presentation architecture.

This document is intended to be operational. Each stage should be narrow enough
to become one or more bounded agent tasks.

## Guiding Principles

- Build the new system beside the current one rather than mutating the old
  pipeline in place.
- Preserve determinism at every stage.
- Prefer vertical slices over broad incomplete rewrites.
- Make each stage produce a usable artifact, not just scaffolding.
- Do not build the final frontend before the canonical and presentation
  contracts are stable.
- Keep the first public release goal in view: a polished standalone Astro-based
  storytelling experience.

## Stage Readiness

- Stage 1: implementation-ready
- Stage 2: implementation-ready
- Stages 3 to 6: implementation-ready under the locked identity and provenance
  contracts
- Stages 7 and 8: implementation-ready as downstream stages after the canonical
  and presentation prerequisites are in place

## Recommended Build Order

1. repo restructuring and scaffolding
2. evidence layer foundation
3. canonical event foundation
4. canonical asset and tenure modeling
5. pick lifecycle modeling
6. event-asset flow construction
7. presentation contract generation
8. editorial/context overlays
9. new frontend visualization
10. migration and retirement of old paths

## Stage 0: Repo Restructuring And Scaffolding

### Objective

Create the file and module structure for the redesign without breaking the
current repo.

### Deliverables

- new source directories for redesign modules
- docs alignment with planning files
- tests directory scaffold
- migration/bootstrap location for new SQL
- clear naming convention separating legacy code from redesign code

### Suggested Structure

- `agent-context/`
- `docs/`
- `src/evidence/`
- `src/canonical/`
- `src/presentation/`
- `src/editorial/`
- `src/shared/`
- `sql/`
- `tests/`

### Notes

- This stage should not implement business logic yet.

## Stage 1: Evidence Layer Foundation

### Objective

Implement the first real storage and ingestion layer for:

- raw source capture
- normalized claims
- overrides

### Deliverables

- SQL bootstrap for `evidence.*`
- Python models or query helpers for evidence objects
- one ingestion path from current source inputs into `evidence.source_records`
- first normalization pass into `evidence.normalized_claims`
- override loading mechanism from local structured files or DB

### Scope Recommendation

Start with the smallest meaningful set:

- Spotrac transactions
- Spotrac contracts if useful
- `nba_api` draft history

### Exit Criteria

- the repo can ingest source evidence into the new schema
- claims are queryable independently of canonical lineage logic
- manual overrides can be stored without mutating evidence

## Stage 2: Canonical Event Foundation

### Objective

Build the canonical event timeline for Memphis.

### Deliverables

- SQL bootstrap for `canonical.events` and event provenance
- canonical event builder from evidence + overrides
- explicit same-day event ordering support
- event merge logic for compound transactions

### Scope Recommendation

Focus only on canonical events first, not full asset reconstruction.

The system should be able to answer:

- what happened on a given day?
- what is the ordered Memphis event timeline?

### Exit Criteria

- canonical events are deterministic
- event ordering is explicit
- provenance is preserved

## Stage 3: Player Identity And Tenure Modeling

### Objective

Build the player side of the canonical asset model.

### Deliverables

- `canonical.player_identity`
- `canonical.player_tenure`
- player-related canonical asset registry decisions implemented
- contract and roster-status state handling for players

### Scope Recommendation

Do not solve picks in this stage.

Focus on:

- signings
- waivers
- re-signings
- returns after absence
- tenure interval boundaries

### Exit Criteria

- player Memphis presence is modeled as distinct tenures
- a player can leave and later return without false continuity
- player-related state is date-reconstructable

## Stage 4: Pick Lifecycle Modeling

### Objective

Implement the continuous Memphis pick lifecycle.

### Deliverables

- `canonical.pick_asset`
- pick state transitions across:
  - future pick
  - resolved slot
  - drafted player stage
- provenance for pick identity and metadata
- support for protections metadata

### Scope Recommendation

Do not attempt full protection simulation yet.

The goal is to represent:

- what pick Memphis owned
- what slot it became
- what player it turned into

### Exit Criteria

- pick continuity is preserved through the draft lifecycle
- draft transitions are represented canonically

## Stage 5: Event-Asset Flow Construction

### Objective

Build the lineage core: how assets flow into and out of events.

### Deliverables

- `canonical.event_asset_flow`
- support for compound trade semantics
- player and pick participation in one shared event flow model
- initial lineage integrity checks

### Scope Recommendation

This should be the first stage where the full franchise asset transformation
network becomes visible.

### Exit Criteria

- trades are modeled as one compound event
- outgoing and incoming Memphis assets are explicit
- draft events connect pick lifecycle to player lifecycle

## Stage 6: Presentation Contract Generation

### Objective

Derive the frontend-ready timeline structures from canonical data.

### Deliverables

- `presentation.timeline_nodes`
- `presentation.timeline_edges`
- `presentation.asset_lanes`
- export pipeline for JSON artifacts used by the frontend

### Scope Recommendation

Start with deterministic generation only.

No heavy design work yet. The purpose is to prove that the canonical model can
feed the intended visualization without ad hoc frontend interpretation.

### Exit Criteria

- the new presentation dataset can render a time-based lineage graph
- lane assignment is deterministic
- daily event ordering is preserved in output

## Stage 7: Editorial And Context Overlays

### Objective

Add the non-lineage context needed for the storytelling product.

### Deliverables

- `editorial.annotations`
- `editorial.calendar_markers`
- `editorial.game_overlays`
- `editorial.eras`

### Scope Recommendation

The first pass can be data-only without a polished editing interface.

Structured files or manual inserts are acceptable initially.

### Exit Criteria

- the timeline can be enriched with context beyond transactions
- editorial content remains cleanly separated from canonical lineage truth

## Stage 8: Frontend Vertical Slice

### Objective

Build the first real visualization using the new presentation contract.

### Deliverables

- frontend scaffold
- timeline rendering of player and pick lines
- event nodes with hover/detail states
- deterministic lane display
- support for date navigation and filtering

### Scope Recommendation

Keep the first frontend slice narrow and honest:

- one view
- basic interaction
- clear validation of the data contract

This is not yet the final editorial polish stage.

### Exit Criteria

- the redesigned data model is visibly working end-to-end
- the frontend does not need custom semantic hacks to interpret lineage

## Stage 9: Historical Backfill And QA

### Objective

Scale the redesigned pipeline across the intended Memphis history and validate
it against known franchise events.

### Deliverables

- backfill scripts or rerunnable jobs
- reference scenarios for major Memphis transactions
- validation queries and snapshot tests
- manual audit workflow for ambiguous cases

### Scope Recommendation

This stage should focus on correctness, not new features.

### Exit Criteria

- the new lineage model holds up across the target time range
- major Memphis historical events are represented correctly

## Stage 10: Old Pipeline Retirement

### Objective

Retire or archive the legacy Bronze/Silver/Gold path once the replacement is
trusted.

### Deliverables

- updated repo entrypoints
- updated README
- archival or deletion plan for old pipeline modules
- migration notes for existing exports and DB users

### Exit Criteria

- new architecture is the default path
- legacy path is clearly deprecated or removed

## Recommended First Implementation Sequence

If building now, the most practical first sequence is:

1. Stage 0
2. Stage 1
3. Stage 2
4. Stage 3
5. player-only presentation smoke test
6. Stage 4
7. Stage 5
8. true Stage 6 contract validation

Reason:

- it proves the redesign early without pretending pick continuity is already
  solved
- it validates player tenure separately from the full lineage promise
- it reserves true contract validation for the point where event flow and pick
  continuity actually exist

## Stage Ownership By Area

To keep agent tasks singular and bounded, stage work should usually be assigned
by write scope.

Examples:

- one task for SQL bootstrap
- one task for evidence ingestion modules
- one task for canonical event builder
- one task for player tenure builder
- one task for presentation export builder

Avoid combining:

- schema redesign
- canonical logic
- frontend implementation

into the same task.

## Suggested Task Granularity

Good task shape:

- one schema bootstrap
- one ingestion adapter
- one canonical builder
- one exporter
- one validation/test slice

Bad task shape:

- “implement the whole redesign”

## Validation Strategy Per Stage

Each implementation stage should include one or more of:

- unit tests
- snapshot outputs
- DB validation queries
- known-history scenario checks

Recommended emphasis:

- event ordering tests
- player leave/return tenure tests
- pick lifecycle tests
- compound trade flow tests

## Likely Immediate Next Docs

After this stage plan, the most useful follow-on planning docs would be:

- `agent-context/README.md`
- `agent-context/stages/01-evidence-layer.md`

The second of those is probably the best next move if implementation is close.

## Recommendation

The next planning artifact should be a stage-specific spec for Stage 1:

- evidence schema bootstrap
- evidence ingestion responsibilities
- normalized claim definitions
- override file format or override table contract

That would be the first doc directly actionable for implementation.
