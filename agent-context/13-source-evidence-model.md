# Source / Evidence Model

## Purpose

Define how raw data sources, manually curated corrections, and canonical lineage
facts should relate in the redesigned system.

This document exists to answer a core architectural question:

How does the project move from imperfect public-source claims to an editorially
trusted Memphis asset lineage dataset?

## Core Principle

Source data is evidence, not truth.

The redesigned system should explicitly separate:

- raw source claims
- normalized source claims
- manual curator overrides
- canonical lineage facts

That separation is required because the final product is a public-facing
storytelling system, not just a raw ingestion pipeline.

## Why This Layer Matters

Public transaction sources are useful but not sufficient on their own.

They can be:

- incomplete
- ambiguously ordered
- inconsistently structured
- wrong or hard to reconcile in edge cases
- limited in how they represent multi-asset compound events

The product therefore needs a model where:

- evidence is preserved
- interpretation is explicit
- curation is allowed
- canonical output remains deterministic

## Proposed Evidence Layers

### Layer 1: Raw Source Capture

This is the minimally transformed record of what an external source said.

Examples:

- Spotrac transaction row
- Spotrac contracts page row
- `nba_api` draft history row
- manually assembled CSV or JSON input from research

Characteristics:

- preserve original field values as closely as possible
- preserve source identity and source URL when available
- preserve ingestion timestamp
- preserve enough context to re-run or audit parsing later

This layer should be append-only or close to append-only.

### Layer 2: Normalized Source Claims

This is a source-specific but cleaner representation of what the raw record is
claiming.

Examples:

- source says event type is `trade`
- source says player is `Mike Conley`
- source says effective date is `2019-07-06`
- source says pick asset is `2024 ORL 2nd`

Characteristics:

- still attributable to a specific source record
- easier to query and reconcile than raw payloads
- not yet canonical truth

This layer is where parsing and structured extraction happen.

### Layer 3: Curator Overrides

This is explicit human correction or editorial supplementation.

Examples:

- correcting same-day order
- splitting or merging source rows into the proper Memphis transaction event
- correcting pick origin or protections wording
- filling in missing counterparties or notes
- attaching explanation for why canonical interpretation differs from source

Characteristics:

- explicit authoring provenance
- reason for override should be recorded
- should never silently replace evidence

This layer is critical for a public editorial product.

### Layer 4: Canonical Facts

This is the final modeled output used by lineage construction and the frontend.

Examples:

- canonical event date and order
- canonical event type
- canonical asset participation in a trade
- canonical player tenure intervals
- canonical pick lifecycle transitions

Characteristics:

- deterministic
- derived from evidence plus overrides
- stable enough for export and visualization

## Proposed Flow

The recommended processing flow is:

1. ingest raw source records
2. normalize them into structured source claims
3. apply curator overrides where needed
4. reconcile into canonical events, assets, and state transitions
5. publish frontend-ready lineage output

This gives the project a repeatable path from source data to editorial truth.

## Source Types

## External Automated Sources

Initial likely inputs:

- Spotrac transactions
- Spotrac contracts
- `nba_api` draft history

These should be treated as evidence providers, not authoritative truth.

## Manual Research Inputs

These are curated inputs created or assembled by the project owner.

Examples:

- manually entered corrections
- structured notes for ambiguous transactions
- curated date-order adjustments
- annotation datasets

Manual research input is not second-class. For some Memphis-specific edge cases,
it may be the most trustworthy source available.

## Editorial / Narrative Inputs

These are not transaction evidence, but they should still live in the broader
evidence ecosystem.

Examples:

- notes on inflection points
- era labels
- links to reporting or external references

These should remain distinct from canonical transaction facts.

## Evidence Object Requirements

Every evidence object should have enough metadata to answer:

- where did this come from?
- when was it captured?
- what does it claim?
- how was it normalized?
- was it overridden?
- what canonical fact did it influence?

Recommended common fields:

- `evidence_id`
- `source_type`
- `source_system`
- `source_locator`
- `captured_at`
- `effective_date_claim`
- `raw_payload`
- `normalized_claim_payload`
- `parser_version`
- `confidence` or `quality_flag`
- `notes`

Not all of these must be user-facing, but they should be available for audit.

## Canonicalization Rules

Canonical facts should not emerge from opaque heuristics alone.

The system should make clear:

- which evidence records contributed
- whether a manual override was applied
- why a final event ordering or asset mapping was chosen

That means canonical objects should be traceable back to evidence.

Recommended principle:

- every important canonical event or transition should be explainable through a
  compact provenance chain

## Reconciliation Strategy

The system should support combining multiple claims into one canonical fact.

Examples:

- Spotrac provides transaction text
- another source or manual input clarifies the exact pick identity
- curator override sets the final event order

Recommended reconciliation policy:

1. preserve all competing evidence
2. normalize into structured claims
3. prefer explicit curation when needed
4. otherwise choose the best-supported deterministic interpretation

## Event-Level Evidence

A canonical event may be backed by one or many evidence records.

Examples:

- one trade event may require multiple source rows
- one draft event may involve both pick-order evidence and selected-player
  evidence
- one waiver may also include buyout metadata

This means the evidence model should support many-to-one relationships:

- many evidence records -> one canonical event

## Asset-Level Evidence

Canonical asset identity and state may also depend on evidence.

Examples:

- player identity resolution across inconsistent source naming
- pick origin and protection metadata
- contract attributes that change after a signing or extension

The system should support:

- many evidence records -> one canonical asset or asset state

## Overrides Model

Overrides should be explicit records, not ad hoc edits.

Each override should ideally include:

- `override_id`
- target object or target claim
- override type
- authored_by
- authored_at
- reason
- replacement or supplemental payload

Override types may include:

- event ordering override
- event merge/split override
- asset identity correction
- pick metadata correction
- source exclusion
- narrative annotation addition

## Source Trust And Priority

This project should avoid pretending there is one universal truth source.

Instead, source trust should be contextual.

Examples:

- Spotrac may be useful for transaction descriptions
- `nba_api` may be useful for draft result structure
- manual research may be preferred for ambiguous Memphis-specific sequencing

Recommended rule:

- trust should be decided per claim type, not only per source system

For example:

- event date claim
- player identity claim
- pick metadata claim
- ordering claim

## Determinism Requirement

Even with manual overrides and multiple sources, the output must remain
deterministic.

That means:

- the same evidence set and override set should produce the same canonical
  lineage output
- canonicalization rules should be versionable
- evidence and override changes should be auditable

## Non-Goals For This Layer

This document does not yet define:

- the final database tables
- the full canonical domain schema
- the final frontend export format

It defines only the evidence and canonicalization contract that those later docs
must honor.

## Design Implications For Schema Work

The next schema redesign should likely include conceptual support for:

- raw evidence records
- normalized claims
- override records
- canonical objects
- provenance links from canonical objects back to evidence

The schema should make it impossible to lose track of where canonical facts came
from.

## Examples

### Example 1: Same-Day Ambiguous Order

Evidence:

- two source records both dated `2019-07-06`
- source does not clearly define sequence

Resolution:

- curator adds an ordering override
- canonical event ordering records that manual curation was used

### Example 2: Draft Pick To Player

Evidence:

- source claim for Memphis owning a future pick
- source claim for final draft slot after lottery/order resolution
- source claim for drafted player on draft night

Resolution:

- canonical pick asset persists through all three stages
- state transitions are tied to evidence records from each phase

### Example 3: Buyout

Evidence:

- source claim indicates waiver-like exit
- additional metadata indicates buyout terms

Resolution:

- canonical lineage behavior matches waiver semantics
- buyout metadata is preserved distinctly in evidence and canonical state where
  available

## Open Questions For Later Docs

These are not blockers for this document, but they shape later schema design:

1. Which claim types deserve their own normalized claim tables or objects?
2. How granular should provenance links be:
   - event-level only
   - asset-state-level too
3. Which override actions should be available through data files versus future
   tooling?
4. Should annotations live in the override system, or in a parallel editorial
   layer?

## Recommendation

The next planning document should be the schema redesign doc.

That doc should map:

- canonical domain objects
- evidence layers
- override mechanics
- provenance requirements

into a concrete storage design for the new system.
