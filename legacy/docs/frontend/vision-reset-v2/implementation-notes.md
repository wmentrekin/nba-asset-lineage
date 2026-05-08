# T1 Implementation Notes

Use [reset-boundary.md](/Users/wentrekin/Documents/nba-asset-lineage/docs/frontend/vision-reset-v2/reset-boundary.md) as the frozen deletion/retention source for all later v2 frontend work.

## What later tasks should enforce

- Do not reintroduce visible `minimap`, `zoom`, `date-window`, `asset filter`, `artifact-state`, `inspector`, or chapter-copy UI.
- Treat `layout_meta.default_window_*`, `layout_meta.minimap_segments`, `chapter_layout.minimap_anchor_id`, and chapter copy fields as load-only residue unless a new plan explicitly changes the contract.
- Keep the visible surface graph-first: `asset_id` continuity, generated geometry, bounded identity markers, and bounded time-appropriate inline labels.
- If implementation reveals that hidden minimap/chapter residue cannot remain internal-only, stop and return to planning instead of inventing a frontend workaround.
