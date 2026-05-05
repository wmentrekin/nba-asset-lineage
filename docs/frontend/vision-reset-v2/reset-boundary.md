# Frontend Vision Reset V2 Boundary

This note freezes the first-slice reset boundary for `frontend-vision-reset-v2`. Implementation tasks after T1 should treat anything outside the keep list as deleted product surface, not deferred chrome.

## Delete visible UI

- `minimap`
- `zoom controls`
- `date-window controls`
- `asset-type filters`
- `artifact-state cards`
- `inspector/debug panel`
- `visible chapter-copy panel`
- `bounded-window viewport state` from the primary render path

## Keep internal only

These inputs may stay loaded for compatibility, but they are visually unused in v2:

- `layout_meta.default_window_*`
- `layout_meta.minimap_segments`
- `chapter_layout.minimap_anchor_id`
- `editorial-chapters.json` chapter `title`
- `editorial-chapters.json` chapter `body`
- `editorial-chapters.json` chapter `order`

## Keep visible

- `canonical.asset.asset_id` continuity
- generated layout geometry, including rendered `segment_id` composition and strand slots
- generated `identity_marker` hints, with stricter bounds handling
- inline strand labels only when time-appropriate and fully bounded inside the local strand/container region

## Guardrails

- The graph starts at the earliest contract date and moves forward through time without a visible bounded-window tool.
- Chapter data is load-only input in the first slice. No visible chapter panel or chapter-driven focus behavior returns in later tasks unless the plan changes.
- Labels and markers must not create false continuity across separate `asset_id` chapters, including leave-and-return or reacquired-player cases.
