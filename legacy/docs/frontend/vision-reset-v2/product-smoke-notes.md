# Frontend Vision Reset V2 Product Smoke Notes

## Result

- `mise run stage8_check`: pass
- `mise exec node@22 -- npm run test -- src/lib/timeline.test.ts`: pass
- `mise run stage8_build`: pass

## Frontend-Verified Behavior

- The built page keeps visible chapter presentation suppressed. No chapter-copy panel returns in the v2 shell.
- The page now leaves only a minimal heading wrapper ahead of the graph.
- The graph renders the full chronology from the earliest generated contract date.
- Reacquired-player fallback markers are hidden when their pills would extend beyond the reacquired segment span.
- Leave-and-return labels stay split across separate `asset_id` segments.
- Pick-to-player visible identity treatment switches at the generated transition link boundary, not before it.

## Frontend Issues

- No owned-scope frontend blocker remains from this T5-T7 pass.

## Upstream Data Limitations

- Real generated exports still do not provide live `two_way` lane rows, so two-way visual treatment cannot be smoke-verified on current Memphis data.
- Real generated exports still do not provide non-empty pick protection summaries, so protection-specific pick labeling cannot be smoke-verified on current Memphis data.
- Real generated editorial data currently exposes a single chapter only. That does not block v2 because chapter presentation is intentionally suppressed, but it limits broader story-flow smoke coverage.
