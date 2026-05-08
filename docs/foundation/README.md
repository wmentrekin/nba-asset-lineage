# Foundation Reset

This folder captures the reset-era foundation for the repo.

The current objective is to define the smallest trustworthy lineage system
before reintroducing higher-order concerns like narrative structure, chaptering,
or editorial overlays.

## Base Output

The base output is a graph-ready data model for a Memphis-only, 10-year asset
lineage page:

- transactions as nodes
- player and pick continuity as strands
- roster state used to validate continuity

## Planned Work Areas

1. define the minimum export contract
2. define the source systems needed for each field
3. define a durable ingestion/storage model in Supabase
4. rebuild the frontend from the smaller contract

## Related Paths

- [`src/foundation/`](../../src/foundation)
- [`src/redesign_cli.py`](../../src/redesign_cli.py)
- [`docs/frontend/`](../frontend)
