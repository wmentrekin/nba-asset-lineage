# Prototype Findings

The current source prototypes are intentionally narrow.

They exist to answer one question:

Can the proposed reset-era source shapes be normalized into the foundation model
without immediately collapsing under obvious format mismatches?

Current answer: yes, for representative examples.

## What Was Prototyped

### Basketball-Reference transaction normalization

Implemented in:

- `src/foundation/prototypes.py`

Tested behaviors:

- split player names from pick text
- infer event type from note text and row shape
- normalize one transaction row into a draft/signing/trade-oriented source event

### NBA stats player and roster normalization

Implemented in:

- `src/foundation/prototypes.py`

Tested behaviors:

- normalize `CommonAllPlayers` rows into `player`
- normalize `CommonTeamRoster` rows into roster-reference entries

### Pick text parsing

Implemented in:

- `src/foundation/prototypes.py`

Tested behaviors:

- draft year extraction
- round extraction
- `via` team extraction
- protection text extraction
- favorability/swap-style text capture

## What Worked

The examples currently support the proposed foundation well enough to continue:

- Basketball-Reference-style rows can normalize into an inclusive `source_event`
  shape
- NBA stats rows can normalize into stable player and roster-reference records
- simple pick text can normalize into:
  - `draft_year`
  - `round_number`
  - `original_team`
  - `protection_text`
  - `swap_text`

## What Is Still Risky

The prototypes do not prove full historical robustness.

Open risks:

- Basketball-Reference rows may vary more across seasons than the prototype
  currently assumes
- player-name parsing from prose will produce edge cases
- multi-pick trade text may be more ambiguous than the tested examples
- some swap/protection language will remain too fuzzy for automatic parsing in
  v1
- source-event grouping still needs a real canonical grouping layer

## Current Conclusion

These prototypes are good enough to justify the next step:

- real source feasibility tests against fetched raw samples

They are not good enough to justify final SQL or ingestion code yet.
