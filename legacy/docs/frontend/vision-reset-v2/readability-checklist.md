# Frontend Vision Reset V2 Readability Checklist

## Checked Surface

- Page shell reduced to a minimal heading plus the graph frame.
- Visible chapter copy remains suppressed.
- Timeline labels and identity markers remain `asset_id`-scoped.

## Frontend Passes

- The page now presents one primary lineage surface instead of a header-plus-support-chrome stack.
- Inline labels render only when the local segment is wide enough to contain them.
- Left identity markers render only when they fit inside the active segment span.
- Leave-and-return and reacquired-player cases stay separated by generated `asset_id` instead of implying person-level continuity.
- Pick-to-player identity treatment changes only at the generated transition boundary.

## Frontend Issues

- No blocking readability defects were found in the owned v2 surface after the T5-T7 pass.

## Upstream Data Gaps

- The current generated layout export contains `0` `two_way` lane segments, so live two-way readability is still unverified from real data.
- The current generated presentation export contains `0` protection-summary-like pick labels, so live pick-protection readability is still unverified from real data.
- The current editorial export contains `1` chapter row only. Chapter presentation is intentionally hidden in v2, but broader chapter sequencing is not yet smoke-tested from upstream data.

## Validation Used

- `mise exec node@22 -- npm run test -- src/lib/timeline.test.ts`
- `mise run stage8_check`
- `mise run stage8_build`
