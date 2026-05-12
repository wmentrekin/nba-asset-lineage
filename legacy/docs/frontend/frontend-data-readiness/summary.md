# Frontend Data Readiness Summary

- Overall status: weak
- Workflow start time: 2026-05-06T02:38:02.782947+00:00
- Freshness gate passed: True

## Row Status
- main_roster: ready
- two_way: weak
- future_picks: ready
- pick_protections_swaps: weak
- pick_to_player: ready
- leave_and_return: ready
- reacquired_players: ready
- chapter_rows: weak
- chapter_focus_fields: weak
- identity_markers: weak

## Population Gaps
- two_way: presentation lane_group count=0; layout lane_group count=0
- pick_protections_swaps: non-null protection_summary count=0; non-empty protection_payload count=0
- chapter_rows: editorial chapter rows=1; chapter_layout rows=1
- chapter_focus_fields: chapter_layout rows with populated focus fields=0
- identity_markers: identity markers with image_path=0; headshot_text=0; text_only=302

## Alignment Gaps
- chapter_rows: frontend/src/lib/timeline.test.ts::loads the generated artifacts without missing asset, event, or chapter references -> file exists
- chapter_focus_fields: frontend/src/lib/timeline.test.ts::keeps editorial chapter title, body, and dates additive instead of sourcing scene windows from chapter_layout -> file exists

## Strengths
- main_roster: presentation lane_group count=270; layout lane_group count=270
- future_picks: presentation lane_group count=32; layout lane_group count=32
- pick_to_player: pick_to_player transition_links=16; drafted_player_name values=16
- leave_and_return: Wayne Selden (SG) spans distinct asset_ids with a visible date gap
- reacquired_players: Dusty Hannahs (G) has a later reacquired segment shorter than the earlier exported tenure
