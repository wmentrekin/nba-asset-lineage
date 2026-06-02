# Frontend Reset

The active frontend now renders from a derived visualization export instead of
the older browser-derived graph scaffold.

Current assumptions:

- Astro remains the host framework
- the first real page is a single graph-first Memphis lineage surface
- narrative, chaptering, minimaps, and editorial overlays are out of scope for
  the base reset
- browser-side code renders precomputed lane/event/segment/connector truth
  rather than recomputing roster layout from raw foundation data

Active artifact and command surface:

- generated artifact:
  [`frontend/src/data/generated/visualization-graph.json`](../../frontend/src/data/generated/visualization-graph.json)
- empty export scaffold:
  `./.venv/bin/python -m redesign_cli show-visualization-export`
- live export:
  `./.venv/bin/python -m redesign_cli export-visualization-graph --output-path frontend/src/data/generated/visualization-graph.json`
- live baseline:
  `./.venv/bin/python -m redesign_cli inspect-visualization-graph-baseline`

The previous frontend exploration and prototype artifacts have been archived
under [`legacy/docs/frontend/`](../../legacy/docs/frontend).

Active model doc:

- [`visualization-implementation-brief.md`](visualization-implementation-brief.md)
- [`visualization-model.md`](visualization-model.md)
- [`visualization-export-schema.md`](visualization-export-schema.md)
- [`visualization-algorithm-spec.md`](visualization-algorithm-spec.md)
