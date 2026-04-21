# Stage 02 Canonical Event Spec

## Purpose

Define how Stage 2 builds the canonical Memphis event timeline from evidence and
overrides.

This stage is responsible for producing ordered, provenance-backed canonical
events. It is not yet responsible for full asset lineage reconstruction.

## Stage Objective

At the end of Stage 2, the system should be able to answer:

- what Memphis-relevant event happened on a given date
- how same-day events are ordered
- which source claims and overrides support each canonical event

## In Scope

- canonical event schema objects
- event clustering and merge rules
- event ordering rules
- provenance linking from canonical events to evidence and overrides
- first canonical event builder

## Out Of Scope

- player tenure intervals
- pick lifecycle continuity
- full event-to-asset lineage flow
- presentation-layer exports

## Core Outputs

- `canonical.events`
- `canonical.event_provenance`
- one deterministic event-building command or job

## Event Definition

A canonical event is a Memphis-relevant dated transformation point.

In v1, likely event types include:

- `trade`
- `draft`
- `signing`
- `waiver`
- `buyout`
- `extension`
- `re_signing`
- `pick_conveyance`

## Canonical Event Requirements

Every canonical event should have:

- `event_id`
- `event_type`
- `event_date`
- `event_order`
- `event_label`
- `description`
- provenance back to source claims and overrides

Optional but recommended:

- `transaction_group_key`
- `is_compound`
- `notes`

## Event Build Inputs

Stage 2 consumes:

- `evidence.source_records`
- `evidence.normalized_claims`
- `evidence.overrides`
- `evidence.override_links` if implemented

## Event Build Steps

### Step 1: Gather Event-Relevant Claims

Collect evidence claims related to:

- event date
- event type
- event description
- transaction counterparty
- event order hint

### Step 2: Form Event Candidate Clusters

Group source claims that likely describe the same Memphis event.

Examples:

- multiple rows describing the same trade package
- multiple claims supporting the same signing
- pick-order and player-selection claims that belong to the same draft event

### Step 3: Assign Candidate Cluster Keys

The event builder should assign a deterministic candidate cluster key before
final merge decisions.

Recommended initial cluster key components:

- source system
- event date
- normalized event type when available
- primary player or pick hint when available
- transaction text hash fallback

This key is not canonical event identity. It is a builder staging key.

### Step 4: Apply Overrides

Overrides may:

- merge clusters
- split clusters
- exclude bad claims
- set or refine same-day order
- clarify event type

Override definitions are curated build inputs, not canonical builder source code.
The initial implementation stores these inputs as versioned files under
`configs/data/` and loads them into `evidence.overrides` before canonical event
building. The builder should remain generic: it applies supported override types
such as `merge_event_cluster`, but it should not hard-code individual Memphis
transaction corrections in transformation logic.

### Step 5: Resolve Canonical Event Identity

Produce one stable canonical event row per final cluster.

### Step 6: Resolve Same-Day Order

Apply the confirmed rule:

1. manual curation when needed
2. source order as fallback

### Step 7: Write Event Provenance

Record which claims, source records, and overrides contributed to each event.

## Clustering Rules

Stage 2 should keep clustering conservative.

Preferred approach:

- only merge records when there is strong evidence they describe the same
  Memphis event
- let overrides handle ambiguous cases

Examples of reasonable merge signals:

- same date
- same event type
- same player or pick references
- source text clearly referring to one transaction package
- same explicit `claim_group_hint`

Examples of dangerous assumptions:

- merging by date alone
- merging all trade-related rows on a single day automatically

Conditions that should force manual override rather than builder inference:

- same-day multi-row evidence that could represent multiple separate events
- conflicting event types across the same candidate cluster
- draft evidence where pick and player evidence disagree on linkage
- sign-and-trade style evidence that cannot be safely merged from Memphis-side
  clues alone

V1 scope note:

- sign-and-trades and multi-team trades are intentionally handled in a
  Memphis-simplified way
- Stage 2 should cluster and resolve them only to the level needed for accurate
  Memphis-side event identity and ordering

## Ordering Rules

### Rule 1: Date Is Primary

Events are ordered first by `event_date`.

### Rule 2: Manual Order Wins

If an override sets explicit same-day order, use it.

### Rule 3: Source Order Fallback

If no manual override exists, preserve source order where the source gives one.

Ordering data contract:

- evidence layer must preserve `source_sequence` where available
- override payloads must support explicit `event_order`
- canonical events must store dense same-day `event_order`
- provenance must record whether order came from:
  - override
  - source fallback
  - deterministic fallback

### Rule 4: Determinism Required

If source order is unavailable or unstable, the builder must still choose a
deterministic fallback, such as a stable cluster key sort.

## Compound Events

Stage 2 should support compound transaction events at the event level even
before full asset flow logic exists.

In practice:

- one trade should become one canonical event
- it may still be backed by many evidence claims
- if this requires curation, the merge decision should be represented by an
  override record and event provenance should reference the `override_id`

This stage only establishes the event object, not the asset flow details.

## Event Provenance Requirements

Every canonical event should be traceable to:

- one or more source records
- one or more normalized claims
- zero or more overrides

Recommended provenance roles:

- `event_date_support`
- `event_type_support`
- `event_description_support`
- `event_order_support`
- `event_merge_support`

## Minimal Validation

Stage 2 should validate:

- no duplicate canonical event IDs
- same-day order is unique within a date
- every canonical event has supporting provenance
- excluded claims do not still drive canonical output

## Test Scenarios

Minimum useful tests:

- simple signing event
- waiver event
- same-day ambiguous ordering with override
- same-day ordering without override using source fallback
- multi-row trade merged into one canonical event
- draft event clustered from separate pick-order and selected-player evidence
- same-day separate transactions that must not auto-merge

## Worked Examples

### Example 1: Multi-Row Trade

- several evidence rows reference one Memphis trade package
- builder assigns the same candidate cluster key from date, type, and grouping
  hints
- no override needed
- one canonical trade event is produced

### Example 2: Ambiguous Same-Day Transactions

- two transaction clusters share one date
- source sequence exists but is editorially wrong or incomplete
- override sets final dense order
- provenance records `event_order_override`

### Example 3: Draft Event From Different Sources

- one source provides resolved pick slot
- one source provides drafted player
- builder links them into one draft candidate cluster only if date, pick hints,
  and grouping hints align
- if not, manual override is required

## Deliverable Checklist

Stage 2 is complete when:

- canonical event tables exist
- event builder writes deterministic rows
- same-day ordering works
- provenance is queryable
- tests cover ordering and clustering basics

## Next Dependency

Stage 3 should consume canonical events to build player identity and tenure
intervals.
