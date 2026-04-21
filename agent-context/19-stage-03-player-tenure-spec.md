# Stage 03 Player Tenure Spec

## Purpose

Define how Stage 3 models player identity and Memphis-visible tenure intervals
on top of canonical events.

## Stage Objective

At the end of Stage 3, the system should be able to represent:

- stable player identity
- distinct Memphis tenure chapters
- date-bounded player presence on the Memphis graph
- player state changes tied to canonical events

## In Scope

- `canonical.player_identity`
- `canonical.player_tenure`
- graph-visible asset registration for player tenures
- player state intervals relevant to Memphis presence

## Out Of Scope

- pick lifecycle continuity
- full compound event asset flow
- frontend lane assignment

## Core Modeling Decision

This stage uses the confirmed split:

- `player_identity`
- `player_tenure`

`player_identity` is the stable person.

`player_tenure` is the Memphis-visible interval or chapter.

Implementation rule:

- every `player_tenure` must create one `canonical.asset` row
- that graph-visible asset row must use:
  - `asset_kind = player_tenure`
  - `player_tenure_id` populated

## Player Identity Requirements

Each player identity should support:

- stable ID
- display name
- optional external identifiers
- identity provenance

Recommended fields:

- `player_id`
- `display_name`
- `normalized_name`
- `nba_person_id`
- `created_at`
- `updated_at`

## Player Tenure Requirements

Each tenure should support:

- link to one player identity
- start date
- end date
- entry event
- exit event when known
- tenure type or roster path metadata

Recommended fields:

- `player_tenure_id`
- `player_id`
- `tenure_start_date`
- `tenure_end_date`
- `entry_event_id`
- `exit_event_id`
- `tenure_type`
- `created_at`
- `updated_at`

## Tenure Construction Rules

### Rule 1: Entry Creates Tenure

A signing, draft selection, trade acquisition, or other Memphis acquisition
event can open a tenure interval.

### Rule 2: Exit Closes Tenure

A trade away, waiver, buyout, release, or other exit event closes a tenure
interval.

### Rule 3: Re-Entry Creates New Tenure

If a player leaves Memphis and later returns, that must create a new
`player_tenure`.

### Rule 4: Continuous Presence Should Not Be Broken Without Cause

Contract modifications that do not remove the player from Memphis presence
should not open a new tenure by default.

## State Modeling

Player-related mutable state should be stored separately from tenure identity.

Examples:

- contract terms
- two-way status
- roster designation
- waiver metadata
- buyout metadata
- waived-and-stretched metadata
- non-guaranteed decision metadata

These can live in `canonical.asset_state` or an equivalent player-state layer.

Recommended explicit typed states for v1:

- `player_contract_interval`
- `player_roster_eligibility_interval`
- `player_two_way_interval`
- `buyout_metadata_point`
- `player_waived_stretched_interval`
- `player_non_guaranteed_decision_point`

## Initial Tenure-Creating Event Types

Stage 3 should at minimum handle:

- `signing`
- `re_signing`
- `draft`
- `trade` acquisition side

## Initial Tenure-Ending Event Types

Stage 3 should at minimum handle:

- `trade` outgoing side
- `waiver`
- `buyout`

## Identity Resolution

Stage 3 should rely on evidence and overrides for player identity resolution.

It should not depend only on naive player-name matching.

Recommended approach:

- use external person IDs when available
- use overrides for ambiguous identity cases
- keep provenance from player identity back to evidence

## Minimal Validation

Stage 3 should validate:

- a tenure cannot end before it starts
- a player cannot have overlapping Memphis tenures unless explicitly supported
  by a future edge case design
- every tenure has an entry event
- every exit event closes the correct tenure

## Test Scenarios

Minimum useful tests:

- player signs with Memphis and remains active
- player is waived and tenure closes
- player is traded away and later re-signs, producing two tenures
- contract extension updates state without opening a new tenure
- buyout closes tenure and preserves distinct metadata

## Deliverable Checklist

Stage 3 is complete when:

- player identities are canonicalized
- Memphis tenures can be built deterministically
- one graph asset row exists per tenure
- leave/return cases create distinct tenures
- state changes can be attached without breaking tenure continuity

## Next Dependency

Stage 4 should build the pick side of the canonical model with the same level of
continuity and provenance.
