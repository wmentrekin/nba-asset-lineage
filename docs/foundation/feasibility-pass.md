# Feasibility Pass

This document records the first real-sample feasibility check against the
reset-era source prototypes.

The question was:

Can the proposed source shapes normalize real Memphis examples closely enough to
justify building a permanent ingestion layer around them?

## Short Answer

Yes, but only partially.

The source families appear viable for the rebuild, but the current parser logic
is still too naive for direct production ingestion.

## Real Samples Checked

### Basketball-Reference Memphis transactions

Representative live examples were taken from the public Memphis transaction
pages:

- 2023-07-11 pick-heavy trade with Phoenix
- 2024-02-08 three-team trade with Phoenix and Brooklyn
- 2024-01-10 Vince Williams Jr. conversion / Bismack Biyombo waiver

### NBA stats player / roster references

Field shapes were checked against the documented `CommonAllPlayers` and
`CommonTeamRoster` endpoint datasets.

## What Worked

### 1. The broad source split still looks correct

The current foundation split still holds:

- Basketball-Reference is plausible as the chronology spine
- NBA stats is plausible for player and roster reference
- pick text can be extracted from transaction prose

### 2. Player/reference normalization is straightforward

The `CommonAllPlayers` and `CommonTeamRoster` field sets appear sufficient for:

- `player`
- roster-reference validation rows

### 3. Inclusive source-event normalization is viable

Basketball-Reference rows can be turned into a stable inclusive event record
with:

- event date
- event label
- inbound/outbound player names
- inbound/outbound pick text
- raw note text

## What Broke

### 1. Event-type inference is too naive

Real sample:

- `2024-02-08` three-team trade with players and a swap-right pick

Current prototype classified it as `draft` instead of `trade`.

Why:

- the current heuristic overweights the word `draft` inside pick text

Implication:

- event classification must use row structure and trade verbs before looking at
  pick wording

### 2. Multi-sentence pick text is being chunked incorrectly

Real sample:

- `2023-07-11` Phoenix deal with:
  - 2024 first-round swap right
  - 2030 first-round swap right
  - did-not-convey language

Current prototype split this into awkward pick chunks such as:

- `a 2030 1st round draft pick. 2024 1st-rd pick was a right to swap`
- `did not convey 2030 1st-rd pick is a right to swap`

Implication:

- pick parsing must happen at sentence/subsentence level, not just comma-split
  chunking

### 3. Mixed-event days cannot be represented as one flat source row forever

Real sample:

- `2024-01-10`
  - Vince Williams Jr. converted from a two-way contract
  - Bismack Biyombo waived

Current prototype reduced this to a `waiver` event and lost the fact that the
day actually includes two distinct source actions.

Implication:

- one scraped date block may need to produce multiple `source_event` rows
- same-date grouping must happen after source-event extraction, not before

### 4. Pick parser is not yet good enough for obligation interpretation

Real sample outputs showed:

- `2024 1st-rd pick was a right to swap, did not convey`
  - year was captured
  - round was not reliably normalized
  - team ownership was not inferred
  - swap semantics were preserved only as text

- `2025 2nd-rd pick is more favorable of HOU, OKC; became HOU pick`
  - year was captured
  - round shorthand was not normalized
  - the favorability rule was not reliably captured as swap text

Implication:

- v1 normalized text is still acceptable
- but the parser needs better shorthand handling:
  - `1st-rd`
  - `2nd-rd`
  - `more favorable`
  - `least favorable`
  - `did not convey`

## Practical Conclusion

The source plan is still valid.

What is not yet valid is the current parser complexity.

The next implementation should not jump straight to SQL or Supabase ingestion.
It should first build a stronger source-normalization layer with:

1. row splitting into multiple source events when needed
2. trade-first event classification
3. sentence-aware pick text extraction
4. better shorthand normalization for pick language

## Recommendation

Proceed with the current source strategy, but add one intermediate phase before
permanent ingestion:

- build a local normalization workbench over fetched raw samples

That workbench should prove:

- Basketball-Reference row splitting
- source-event extraction for mixed-action dates
- pick text sentence parsing
- Memphis trade grouping hints

Only after that should the repo freeze the permanent ingestion tables.
