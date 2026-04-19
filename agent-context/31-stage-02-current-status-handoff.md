# Stage 2 Current Status Handoff

Last updated: 2026-04-19

## Purpose

This document is a next-session handoff for the redesigned Stage 2 canonical
event work. It records the current live Supabase state, the local override
artifact status, and the important debugging result from the second-pass event
merge overrides.

Do not treat this as a new design document. The source-of-truth contracts remain:

- `agent-context/18-stage-02-canonical-event-spec.md`
- `agent-context/26-canonical-identity-and-reference-contract.md`
- `agent-context/27-provenance-and-build-versioning-contract.md`

The checked-in Bronze/Silver/Gold pipeline remains legacy reference material,
not target architecture.

## Scope Reminder

Current implemented scope is still the redesign path only:

- Stage 1 evidence layer is implemented and live-tested.
- Stage 2 canonical events are implemented and live-tested.
- Stage 3+ should not be started unless explicitly directed.
- Frontend work should not be started from this handoff.
- Memphis Grizzlies remains the only release scope.

## Current Live Database Status

The live Supabase database has the redesign schemas bootstrapped:

- `evidence`
- `canonical`

The live Stage 1 evidence build has been run against the Supabase database.
Current evidence counts:

- `evidence.source_records`: `486`
- `evidence.normalized_claims`: `3287`
- `evidence.overrides`: `19`

The live Stage 2 canonical event build has been rebuilt after loading all 19
event merge overrides. Current canonical counts:

- `canonical.events`: `442`
- `canonical.event_provenance`: `1845`
- `canonical.event_provenance` rows with `provenance_role = 'event_merge_support'`: `19`

The latest validation result:

```text
validate-canonical-events: success
errors: []
warnings: []
event_count: 442
provenance_count: 1845
```

## Override Directory Status

The `overrides/` directory currently contains:

- `overrides/.gitkeep`
- `overrides/README.md`
- `overrides/stage2_event_merge_overrides.yaml`

Only `overrides/.gitkeep` was tracked before this handoff work.

`overrides/stage2_event_merge_overrides.yaml` should be kept and committed. It
is not a disposable debug artifact. It is the curated Stage 2 event merge
override bundle required to reproduce the current canonical event output.

`overrides/README.md` documents the operational rule for this directory: do not
place scratch YAML or JSON files under `overrides/` unless they are valid
pipeline inputs that should be loaded.

The `.gitkeep` file is harmless. Once the YAML override file is tracked, `.gitkeep`
is no longer technically required, but it can remain in place.

## How Override Loading Works

The redesign override loader is implemented in:

- `src/evidence/overrides.py`

The loader recursively reads these file types from the configured override path:

- `*.json`
- `*.yaml`
- `*.yml`

The default CLI override path is `overrides`.

These CLI commands use that path:

```bash
uv --cache-dir /tmp/uv-cache run python -m redesign_cli build-evidence --overrides-path overrides
uv --cache-dir /tmp/uv-cache run python -m redesign_cli load-overrides --overrides-path overrides
```

Because every JSON/YAML file under `overrides/` is loaded, curated override files
in that directory are part of the reproducible build input. Temporary notes,
scratch JSON, or alternative inactive bundles should not be stored there unless
they are intentionally valid override inputs.

Override bundle payloads are validated with Pydantic before conversion into the
Stage 1 `OverrideRecord` / `OverrideLink` dataclasses.

## Current Override Bundle

`overrides/stage2_event_merge_overrides.yaml` contains 19 active overrides.

All 19 are `merge_event_cluster` overrides with:

- `target_type`: `event_cluster`
- `payload.source_cluster_keys`: the source event cluster keys to merge
- `payload.target_cluster_key`: the canonical cluster key to keep
- `is_active`: `true`

The purpose of these overrides is to merge Spotrac rows that represent one
compound Memphis event but were emitted as multiple incoming-player or
incoming-asset transaction rows.

The override bundle currently produces 19 canonical provenance rows with:

```text
provenance_role = event_merge_support
```

## Second-Pass Override Debug Result

The second-pass overrides were for these dates:

- `2023-07-08`
- `2025-02-06`
- `2025-07-06`
- `2026-02-03`

The initial symptom was that these overrides were active in `evidence.overrides`
and appeared correctly targeted, but persisted `canonical.events` still showed
separate events for their source cluster keys.

The concrete debug check showed:

```text
canonical.event_provenance had no rows for the four second-pass override IDs.
```

Further checks showed:

- The four overrides were present in `evidence.overrides`.
- The overrides were active.
- Their `target_type`, `target_key`, and payloads were correctly shaped.
- Every listed source cluster key existed in `evidence.normalized_claims.claim_group_hint`.
- The then-current `canonical.events` rows still contained the unmerged source cluster keys.

Running the current Stage 2 builder in memory against live inputs produced the
correct result:

```text
event_count: 442
provenance_count: 1845
second-pass override provenance: present
merge-support provenance count: 19
```

Conclusion: the persisted canonical tables were stale. The issue was not bad
override targeting and not a builder logic bug.

After running:

```bash
uv --cache-dir /tmp/uv-cache run python -m redesign_cli build-canonical-events --builder-version stage2-events-v1
```

the live canonical tables matched the in-memory result.

## Confirmed Second-Pass Merge Results

After rebuilding Stage 2, each second-pass override appears once in
`canonical.event_provenance` with `provenance_role = 'event_merge_support'`:

```text
override_merge_event_2023_07_08_five_team_trade: 1
override_merge_event_2025_02_06_washington_trade: 1
override_merge_event_2025_07_06_golden_state_trade: 1
override_merge_event_2026_02_03_utah_trade: 1
```

Date-level canonical event counts after rebuild:

```text
2023-07-08: 2 events, 1 trade
2025-02-06: 1 event, 1 trade
2025-07-06: 1 event, 1 trade
2026-02-03: 1 event, 1 trade
```

`2023-07-08` still has 2 total events because only one of them is the merged
trade event targeted by the override set.

## Current Implementation Files

Stage 2 implementation files:

- `sql/redesign/0002_canonical_events_bootstrap.sql`
- `src/canonical/models.py`
- `src/canonical/events.py`
- `src/canonical/validate.py`
- `tests/canonical/test_events.py`
- `tests/canonical/test_validation.py`

Stage 1 override loading support:

- `src/evidence/overrides.py`
- `src/evidence/models.py`
- `src/redesign_cli.py`

Current override data file:

- `overrides/stage2_event_merge_overrides.yaml`

## Commands Known To Pass

Local test suite:

```bash
uv --cache-dir /tmp/uv-cache run pytest tests/evidence tests/canonical
```

Expected result:

```text
16 passed
```

Compile check:

```bash
uv --cache-dir /tmp/uv-cache run python -m compileall src tests
```

Live canonical validation:

```bash
uv --cache-dir /tmp/uv-cache run python -m redesign_cli validate-canonical-events
```

Expected live result:

```text
status: success
event_count: 442
provenance_count: 1845
errors: []
warnings: []
```

## Next Session Recommendations

Start by checking worktree state:

```bash
git status --short
```

If the override handoff work has not been committed yet, expected important
items include:

```text
 M tests/canonical/test_events.py
 M tests/evidence/test_overrides_and_validation.py
 M src/evidence/overrides.py
 M pyproject.toml
 M uv.lock
?? overrides/README.md
?? overrides/stage2_event_merge_overrides.yaml
?? src/evidence/override_schema.py
```

Recommended next action:

1. Review `overrides/stage2_event_merge_overrides.yaml`.
2. Review the Pydantic override validation model and reproducibility tests.
3. Commit the override file and validation support if they match the intended curated Stage 2 behavior.
4. Re-run local tests.
5. Re-run live `validate-canonical-events` if working against Supabase.

Do not delete `overrides/stage2_event_merge_overrides.yaml` unless you intend to
remove the curated event merge behavior from reproducible Stage 2 builds.

## Known Operational Notes

Use `uv` for project commands.

The local environment may show a benign warning that `VIRTUAL_ENV` points to
another project environment. `uv` still uses this project's environment.

Use this cache path to avoid sandbox write issues:

```bash
uv --cache-dir /tmp/uv-cache ...
```

Live Supabase commands require network access. Do not include credentials in
docs, commits, or assistant responses.

The live database name is `postgres`, even though the Supabase project is named
`nba-asset-lineage`.
