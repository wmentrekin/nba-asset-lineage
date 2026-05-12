# Full Dataset Performance Check

Date: 2026-05-01
Feature: `frontend-vision-reset`
Task: `T11`

## Build evidence

- `mise exec node@22 -- npm run build`
  Result: passed on 2026-05-01.
- Client bundle emitted by Astro build:
  - `dist/_astro/index.astro_astro_type_script_index_0_lang.CF164wHu.js`
  - 29.61 kB raw, 8.94 kB gzip
- Built HTML size:
  - `frontend/dist/index.html`: 1,123,722 bytes
  - The large HTML size is primarily the embedded generated contract payload, not decade-wide hidden SVG after the T11 pruning.

## Renderer hardening results

- The active SVG no longer serializes hidden decade-wide node and junction markup into the default viewport.
- Hover/focus inspection now reuses the current layout instead of rebuilding it on every pointer interaction.
- Input-driven rerenders are now frame-coalesced through `requestAnimationFrame`.
- Dense windows now stay inside a bounded scroll shell, so late-dataset slices with triple-digit visible roster rows do not expand the entire page vertically.

## Default built viewport snapshot

- Visible strands: 23
- Visible nodes: 25
- Visible junctions: 25
- Visible inline labels: 11
- Visible identity markers: 24

## Required DevTools trace workflow

Status: blocked in the current sandboxed environment.

Attempted workflow:

1. Build the frontend successfully.
2. Serve `frontend/dist` locally for Chrome/Chromium tracing.
3. Open the built page in Chrome and record initial load, one 180-day traverse, one chapter jump, and one minimap jump.

Observed blocker:

- Local static serving could not be started from the sandbox:

```text
python3 -m http.server 4173 --directory /Users/wentrekin/Documents/nba-asset-lineage/frontend/dist
PermissionError: [Errno 1] Operation not permitted
```

- A follow-up headless Chrome screenshot attempt against the built `file://` URL also failed to produce an output artifact under the same sandbox, so there is no trustworthy browser-side fallback trace in this environment.

Installed browser version:

- `Google Chrome 147.0.7727.138`

## Result

- Code-level and build-level hardening completed.
- Exact DevTools Performance trace collection remains blocked by sandbox restrictions on the required local browser/server workflow.
- Longest observed main-thread task: unavailable until the trace can be collected in an unsandboxed local browser session.
