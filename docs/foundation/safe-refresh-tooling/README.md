# Safe Refresh Operator Guide

This is the local, code-only safety layer for a future Memphis offseason
refresh. It has not captured live sources, opened the live database, run a
refresh, or restored a snapshot. A later live pass still needs its own `$work`
checkpoint and explicit user authorization.

## Sealed artifact leaf

All operational data stays in one newly created, restricted repo-local leaf:
`tmp/<refresh-id>/`. The directory and files must remain private (`0700` for
directories and `0600` for files), symlink-free, and ignored by Git. Never
commit, upload, or attach its raw source bodies, snapshot rows, approvals, or
execution state to a PR.

The leaf has a closed, ordered input chain:

1. `bundles/<source-kind>/` for exactly the supported locked source bundles.
2. `fixtures/<name>.json` for exactly `draft_resolution`,
   `historical_checksum`, `roster_baseline`, and `two_way_status`.
3. `refresh-request.json`, binding the fixed paths, the as-of date, and source
   and fixture digests.
4. `refresh-reconciliation.json`, binding the request to the baseline and
   historical-checksum evidence.
5. `refresh-plan.json`, binding the request and reconciliation to the closed,
   fixed-order typed mutation plans.
6. `projection-report.json`, written once by preview and bound back to the
   request, reconciliation, and plan.

These inputs are created only by reviewed artifact tooling. There is no generic
command that accepts an arbitrary JSON file, SQL, table name, plan step, or
source path. Tampering, drift, malformed codecs, missing slots, or broken
digest links must fail before the preview, runner, or restore command opens a
database connection.

## Operational sequence

1. In the separately authorized live pass, create the leaf and capture the
   full 21-table preimage with:

   ```bash
   uv --cache-dir /tmp/uv-cache run python -m redesign_cli \
     capture-foundation-refresh-snapshot --repo-root . --refresh-id <refresh-id> --execute
   ```

   This reads the database and writes restricted local snapshot material; it
   does not modify database rows. Source capture is also live work, but has no
   generic capture CLI: use the reviewed source-bundle path for that pass.
2. After fixed bundles, fixtures, request, reconciliation, and plan have been
   materialized and reviewed, preview exactly that leaf:

   ```bash
   uv --cache-dir /tmp/uv-cache run python -m redesign_cli \
     preview-refresh-projection --artifact-directory tmp/<refresh-id>
   ```

   Preview validates local inputs before reading one baseline. It writes no
   database rows and refuses to replace an existing projection report; rerun in
   a new leaf instead.
3. Review the sanitized report and record a human-supplied approval. The
   approval input is an externally reviewed closed `refresh_approval_v1`
   document; this command validates and records it but cannot create consent:

   ```bash
   uv --cache-dir /tmp/uv-cache run python -m redesign_cli \
     record-refresh-approval --artifact-directory tmp/<refresh-id> \
     --approval-input-path <reviewed-approval.json>
   ```

   An `action=execute_refresh` approval binds the exact sealed chain, snapshot,
   projection, implementation, environment, dirty tree, table/schema/database,
   and prefix fingerprints.
4. Only after a separate user go-ahead, run the already approved plan:

   ```bash
   uv --cache-dir /tmp/uv-cache run python -m redesign_cli \
     run-approved-foundation-refresh --artifact-directory tmp/<refresh-id> --execute
   ```

   The runner cannot select, skip, or reorder steps. Any changed input or
   unreconcilable prefix stops in `needs_restore` rather than guessing.
5. Restore is a separate destructive operation. It needs a newly recorded
   `action=restore_snapshot` approval; an execution approval is never enough:

   ```bash
   uv --cache-dir /tmp/uv-cache run python -m redesign_cli \
     restore-foundation-refresh-snapshot --artifact-directory tmp/<refresh-id> --execute
   ```

## Retention and limitations

Keep the leaf only through the explicit refresh review and recovery window;
then perform a separately reviewed local cleanup. The advisory lock coordinates
only this runner, not legacy direct writers. Any bundle, fixture, code,
dependency, environment, dirty-tree, schema/database, approval, or prefix
drift invalidates approval and requires a fresh projection and approval.

Local verification on this branch is offline and fixture/fake-connection only.
Frontend checks require an existing dependency-ready `frontend/node_modules`;
the task does not install dependencies to force those checks.
