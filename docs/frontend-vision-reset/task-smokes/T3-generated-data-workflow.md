# T3 Generated Data Workflow

## Canonical regeneration sequence

This phase freezes the repo-local frontend data regeneration order as:

1. `mise run stage6_export`
2. `mise run stage8_layout_export`
3. `mise run stage8_chapter_export`

Expected artifact targets:

- `frontend/src/data/generated/presentation-contract.json`
- `frontend/src/data/generated/layout-contract.json`
- `frontend/src/data/generated/editorial-chapters.json`

## Supporting local checks run

- `uv --cache-dir /tmp/uv-cache run pytest -q tests/editorial/test_contract.py tests/presentation/test_layout_contract.py`
  - result: `16 passed in 0.44s`
- `uv --cache-dir /tmp/uv-cache run pytest -q tests/presentation`
  - result: `16 passed in 0.31s`
- `uv --cache-dir /tmp/uv-cache run python -m redesign_cli --help`
  - result: includes `export-editorial-chapters`
- `mise tasks ls | rg "stage6_export|stage8_layout_export|stage8_chapter_export"`
  - result: all three export tasks are present
- `uv --cache-dir /tmp/uv-cache run python - <<'PY' ... load_override_bundle("configs/data") ... PY`
  - result: `{'override_count': 19, 'override_link_count': 0}`
- `python - <<'PY' ... validate_layout_contract(...) against frontend/src/data/generated/presentation-contract.json and layout-contract.json ... PY`
  - result: `{'ok': True, 'errors': 0, 'warnings': 0}`

## Full regeneration attempt

Attempt date: `2026-04-29`

Command attempted:

```bash
mise run stage6_export
```

Observed result:

- task startup succeeded and resolved the new output path
- export failed before writing `frontend/src/data/generated/presentation-contract.json`
- exact blocker:

```text
psycopg.OperationalError: failed to resolve host 'db.gjotcimniipqwhdgqutp.supabase.co': [Errno 8] nodename nor servname provided, or not known
```

Because Stage 6 export did not complete, the downstream commands were not run:

- `mise run stage8_layout_export`
- `mise run stage8_chapter_export`

## Outcome

The repo-local generated-data workflow is wired and test-covered, but the
end-to-end regeneration smoke is currently blocked in this environment by
database host resolution failure against the configured Supabase host.
