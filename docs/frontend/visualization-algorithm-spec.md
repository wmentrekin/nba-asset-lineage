# Visualization Algorithm Spec

## Purpose

This document defines the algorithmic rules for building the derived
visualization export described in:

- [`visualization-model.md`](visualization-model.md)
- [`visualization-export-schema.md`](visualization-export-schema.md)

This spec answers the remaining implementation-level questions:

- how slots are assigned
- how lanes reflow after events
- how temporary overflow works
- how event grouping works
- how adaptive lead-in and settle-in windows are computed

The goal is to make the future visualization exporter deterministic and
testable.

## Scope

This spec governs the server-side builder for the derived visualization export.

It does not govern:

- pixel rendering
- frontend animation code
- hover/focus UI behavior
- narrative or editorial overlays

## Inputs

The builder should consume the already-locked render-driving foundation inputs:

- `events`
- `player_assets`
- `pick_assets`
- `transitions`
- `daily_roster_states`

It may also consume supporting additive/context surfaces when needed:

- `roster_snapshots`
- `draft_prior_owner_lineages`
- `conditional_pick_families`
- `draft_lottery_results`

## Canonical Ordering

### Day Order

All state should be processed in strict calendar order by day.

### Same-Day Event Order

Within one day, grouped canonical events should be handled in:

1. grouped event identity order
2. canonical event `sequence`
3. stable `event_id` tie-break

The purpose is not to imply rich intra-day truth. It is only to keep the
derived export deterministic.

## Lane Bands

The visualization always uses these player-band partitions:

- main roster: slots `1-15`
- two-way: slots `16-18`
- temporary overflow: dynamic slots below `18`

Pick lanes live below all player-related lanes.

## Core Data Structures

The exporter should conceptually maintain these derived working structures while
building output:

- `day_state`
  - current occupancy by lane
  - current lane by asset
- `player_rank_cache`
  - tenure-based ordering inputs for player assets
- `event_group`
  - same-day grouped node summary
- `pending_event_windows`
  - lead/settle window metadata by asset/event
- `overflow_registry`
  - temporary player eligibility and band participation

These do not need to be final export types. They are implementation scaffolding.

## Player Slot Assignment

### Initial Left-Edge Seed

At the render start date:

1. read the earliest applicable `daily_roster_state`
2. divide players into:
   - standard main-roster players
   - two-way players
   - temporary-overflow players
3. rank each band by:
   - primary: team tenure descending
   - tie-break: stable asset id ascending

Then assign:

- top 15 eligible standard players to slots `1-15`
- up to 3 two-way players to slots `16-18`
- any overflow-eligible temporary players to dynamic overflow slots

### Sacred Slot Rule

Slots are owned by the lane, not by the player.

Implications:

- players do not jump above already-occupied slots
- a player remains in the current slot until the slot is vacated or the
  player's status changes bands

### Daily Occupancy Update

For each new `daily_roster_state` day:

1. compute membership by band:
   - main roster
   - two-way
   - temporary overflow
2. compare against prior day occupancy
3. identify:
   - retained players
   - departing players
   - arriving players
   - band-change players

Retained players keep their existing slot whenever valid.

## Main-Roster Reflow

### Departures

When a main-roster player leaves the band:

1. vacate the slot
2. shift every lower occupied main-roster slot upward by one
3. preserve relative order among the shifted players

This is the default reflow rule.

### Arrivals

When a new main-roster player enters the band:

1. find the highest available open main-roster slot
2. assign the player there

New arrivals must not jump above an already-occupied slot.

### Band Changes

If a player changes from one band to another:

1. treat the player as a departure from the old band
2. reflow the old band
3. treat the player as an arrival into the new band

This avoids silent cross-band lane reuse.

## Two-Way Reflow

Two-way slots behave like a smaller sacred sub-band.

Rules:

- two-way players occupy only slots `16-18`
- retained two-way players keep their slot if still valid
- if a two-way slot vacates, lower occupied two-way slots shift upward within
  the two-way band only
- incoming two-way players take the highest open two-way slot

Two-way reflow must not disturb main-roster slots `1-15`.

## Temporary Overflow Rules

### Purpose

The temporary overflow band exists to isolate short-term roster noise from the
core visual structure.

Typical eligible cases:

- 10-day contracts
- hardship signings
- similarly temporary short-lived roster additions

### Entry Rule

A player should enter temporary overflow instead of the main bands when:

1. the roster status is not main-roster stable
2. the contract/action type is explicitly temporary, or
3. the configured temporary-status classifier marks the player as overflow
   eligible

### Persistence Rule

Overflow occupants should preserve relative order across retained days whenever
possible.

### Exit Rule

A temporary-overflow player exits the overflow band when:

- the player departs the team entirely, or
- the player's status becomes a stable main-roster or two-way occupancy state

If a player converts into a stable roster state:

1. remove from overflow
2. reflow overflow upward
3. treat the player as an arrival into the target stable band

### Overflow Ordering

Overflow entrants should be ranked by:

1. entry date ascending
2. tenure descending
3. stable asset id ascending

This should keep temporary churn deterministic without overfitting importance.

## Pick Lane Assignment

### Eligibility

A pick becomes eligible for rendering when it is:

1. tradeable under league rules, and
2. relevant to Memphis through actual ownership, obligation, swap right,
   encumbrance, or bounded conditional-family context

### Pick Band Ordering

Pick lanes should be ordered deterministically by:

1. draft year ascending
2. round number ascending
3. original team code ascending
4. stable asset id ascending

### Pick Occupancy

Pick occupancy should follow loaded pick-truth state rather than inferred
frontend behavior.

The lane assignment should preserve continuity for a pick across time unless the
pick converts at draft or leaves Memphis-relevant scope.

## Event Grouping

### Grouping Rule

Events should be grouped into one visual node when:

1. they occur on the same day, and
2. they belong to the same canonical/source group context, or
3. they represent one coherent same-day transaction cluster for the base graph

### Grouped Node Payload

A grouped node should aggregate:

- inbound assets
- outbound assets
- event type
- compact label
- sent summary
- received summary

### Same-Day Draft Handling

Draft pick-to-player conversions should be grouped by draft-day event context,
but each pick-to-player handoff must still remain individually traceable.

## Event Geometry Windows

### Principle

Lead-in and settle-in windows should be adaptive, not fixed.

They should respond to local event density while staying within bounded clamps.

### Definitions

For an asset touching event `E`:

- `prev_gap_days`: days since the previous event involving that asset
- `next_gap_days`: days until the next event involving that asset

### Lead-In Window

For outgoing or moving assets, compute:

```text
raw_lead = floor(sqrt(prev_gap_days) * lead_scale)
lead_window_days = clamp(raw_lead, LEAD_MIN_DAYS, LEAD_MAX_DAYS)
```

Recommended starting constants:

- `LEAD_MIN_DAYS = 4`
- `LEAD_MAX_DAYS = 21`
- `lead_scale = 3`

Interpretation:

- nearby events shorten the approach
- quiet spans allow longer smoother curves

### Settle-In Window

For incoming or moving assets, compute:

```text
raw_settle = floor(sqrt(next_gap_days) * settle_scale)
settle_window_days = clamp(raw_settle, SETTLE_MIN_DAYS, SETTLE_MAX_DAYS)
```

Recommended starting constants:

- `SETTLE_MIN_DAYS = 2`
- `SETTLE_MAX_DAYS = 8`
- `settle_scale = 1.75`

### Shared-Event Alignment

If multiple assets participate in the same grouped event:

- align their effective lead windows within that group
- align their effective settle windows within that group when possible

Use:

- the maximum computed lead among outgoing event participants
- the maximum computed settle among incoming event participants

This makes multi-asset trades read as one coherent visual gesture.

### Overlap Guard

If two adjacent event windows for the same asset would overlap:

1. shorten the earlier window first
2. then shorten the later window if necessary
3. never violate minimum clamps

If overlap remains even after clamp application:

- allow compressed adjacency
- do not distort calendar time

## Connector Semantics

### Outgoing

Use `outgoing` connectors when:

- a player leaves the roster
- a pick leaves Memphis control
- an asset enters a grouped trade departure

### Incoming

Use `incoming` connectors when:

- a player joins the roster
- a pick enters Memphis control
- an asset enters from a grouped trade arrival

### Conversion

Use `conversion` connectors when:

- a draft pick converts into a player at the draft node

This should produce:

- one pick termination at the node
- one player start at the same node

### Termination

Use `termination` connectors when:

- a player is waived or otherwise ends continuity without a continuing Memphis
  lane

Termination should not imply movement into another unrelated lane.

### Lane Shift

Use `lane_shift` connectors only for slot-band reflow semantics where continuity
should remain explicit through a slot change.

This should be rare and must never imply a transaction by itself.

## Strand Segment Construction

For each asset:

1. build stable occupancy spans from lane truth
2. carve out lead/settle windows around participating events
3. emit:
   - resident segments
   - event lead-in segments
   - event settle-in segments
   - conversion or termination segments where applicable

Segment boundaries must always be traceable to:

- occupancy intervals
- grouped event nodes
- computed lead/settle windows

## Deterministic Tie-Breaks

Whenever multiple valid choices exist, apply these tie-breaks:

1. keep incumbent slot if possible
2. choose the highest available eligible slot
3. preserve prior relative order
4. fall back to stable asset id ascending

This prevents visual drift between identical runs.

## Required Builder Invariants

The builder must validate at least these invariants:

- no player occupies two player lanes on the same day
- no more than 15 main-roster lanes are occupied on one day
- no more than 3 two-way lanes are occupied on one day
- overflow occupants do not silently displace core-band players
- no concrete fallback pick appears simultaneously with its primary branch
- every connector refers to a valid node and valid asset
- every strand segment refers to a valid lane and valid asset
- every draft conversion maps one pick continuity into one player continuity
- same-day grouped nodes do not duplicate the same asset on both sent and
  received sides unless explicitly modeled as a move case
- waiver/termination strands end at the terminating event

## Future Override Hook

The builder should reserve room for a later manual ordering override layer.

The first version should not implement editorial override behavior, but it
should not block a future rule such as:

- explicit slot priority for star/core players
- salary-weighted ordering
- chapter-specific lane freezing

The current version should treat tenure-first ordering as the default policy.

## Implementation Sequence

The eventual build pass should implement the algorithm in this order:

1. normalize grouped event nodes
2. derive daily band membership
3. assign and reflow player lanes
4. assign pick lanes
5. build occupancy intervals
6. compute adaptive event windows
7. build strand segments and connectors
8. enforce invariants
9. emit the derived visualization export

