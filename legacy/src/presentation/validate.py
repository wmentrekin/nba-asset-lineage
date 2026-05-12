from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml

from canonical.models import CanonicalEvent
from editorial.models import EditorialOverlayBuildResult
from presentation.contract import _expected_transition_link_specs
from presentation.models import (
    AssetLane,
    LayoutContractBuildResult,
    PresentationContractBuildResult,
    TimelineEdge,
    TimelineNode,
)


@dataclass(frozen=True)
class PresentationContractValidationReport:
    node_count: int
    edge_count: int
    lane_count: int
    errors: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class LayoutContractValidationReport:
    lane_layout_count: int
    event_layout_count: int
    label_layout_count: int
    chapter_layout_count: int
    errors: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


DEFAULT_FRONTEND_DATA_READINESS_MATRIX_PATH = Path("docs/frontend/frontend-data-readiness/readiness-matrix.yaml")
DEFAULT_FRONTEND_DATA_READINESS_REPORT_PATH = Path("docs/frontend/frontend-data-readiness/readiness-report.yaml")
DEFAULT_FRONTEND_DATA_READINESS_SUMMARY_PATH = Path("docs/frontend/frontend-data-readiness/summary.md")
DEFAULT_FRONTEND_DATA_READINESS_ARTIFACT_PATHS = {
    "presentation-contract.json": Path("frontend/src/data/generated/presentation-contract.json"),
    "layout-contract.json": Path("frontend/src/data/generated/layout-contract.json"),
    "editorial-chapters.json": Path("frontend/src/data/generated/editorial-chapters.json"),
}


@dataclass(frozen=True)
class FrontendDataReadinessRowMatrix:
    row: str
    schema_source_paths: tuple[str, ...]
    schema_supported_rule: str
    json_paths: tuple[str, ...]
    population_rule: str
    frontend_code_paths: tuple[str, ...]
    frontend_test_paths: tuple[str, ...]
    frontend_test_ids: tuple[str, ...]
    frontend_consumed_rule: str


@dataclass(frozen=True)
class FrontendDataReadinessMatrix:
    selector_format: str
    chapter_deferred_rows: frozenset[str]
    rows: tuple[FrontendDataReadinessRowMatrix, ...]


@dataclass(frozen=True)
class FrontendDataReadinessAuditResult:
    report: dict[str, object]
    report_path: Path
    summary_path: Path
    exit_code: int


def _normalize_datetime(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        return result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _parse_selector(selector: str) -> tuple[Path, str]:
    path_part, separator, exact_substring = selector.partition("::")
    if separator != "::" or not path_part or not exact_substring:
        raise ValueError(f"invalid selector {selector!r}; expected relative/path::exact_substring")
    path = Path(path_part)
    if path.is_absolute():
        raise ValueError(f"selector path must be relative: {selector!r}")
    return path, exact_substring


def load_frontend_data_readiness_matrix(
    *,
    matrix_path: Path | str = DEFAULT_FRONTEND_DATA_READINESS_MATRIX_PATH,
) -> FrontendDataReadinessMatrix:
    raw_payload = yaml.safe_load(Path(matrix_path).read_text(encoding="utf-8"))
    if not isinstance(raw_payload, dict):
        raise ValueError("frontend data readiness matrix must be a mapping")
    selector_format = raw_payload.get("selector_format")
    if selector_format != "relative/path::exact_substring":
        raise ValueError("frontend data readiness matrix must use selector_format=relative/path::exact_substring")

    chapter_policy = raw_payload.get("chapter_selector_policy") or {}
    chapter_rows = tuple(chapter_policy.get("applies_to_rows") or ())
    if chapter_policy.get("deferred_selector_satisfaction_until_task") != "T3":
        raise ValueError("chapter_selector_policy must defer selector satisfaction until T3")

    rows_payload = raw_payload.get("rows")
    if not isinstance(rows_payload, list) or not rows_payload:
        raise ValueError("frontend data readiness matrix must declare non-empty rows")

    required_keys = {
        "row",
        "schema_source_paths",
        "schema_supported_rule",
        "json_paths",
        "population_rule",
        "frontend_code_paths",
        "frontend_test_paths",
        "frontend_test_ids",
        "frontend_consumed_rule",
    }
    parsed_rows: list[FrontendDataReadinessRowMatrix] = []
    seen_rows: set[str] = set()
    for row_payload in rows_payload:
        if not isinstance(row_payload, dict):
            raise ValueError("frontend data readiness rows must be mappings")
        missing = sorted(required_keys - set(row_payload))
        if missing:
            raise ValueError(f"frontend data readiness row is missing keys: {', '.join(missing)}")
        row_name = str(row_payload["row"])
        if row_name in seen_rows:
            raise ValueError(f"duplicate frontend data readiness row: {row_name}")
        seen_rows.add(row_name)

        for selector_group in ("schema_source_paths", "frontend_code_paths", "frontend_test_ids"):
            selectors = row_payload[selector_group]
            if not isinstance(selectors, list):
                raise ValueError(f"{row_name}.{selector_group} must be a list")
            for selector in selectors:
                _parse_selector(str(selector))

        for list_group in ("json_paths", "frontend_test_paths"):
            if not isinstance(row_payload[list_group], list):
                raise ValueError(f"{row_name}.{list_group} must be a list")

        parsed_rows.append(
            FrontendDataReadinessRowMatrix(
                row=row_name,
                schema_source_paths=tuple(str(entry) for entry in row_payload["schema_source_paths"]),
                schema_supported_rule=str(row_payload["schema_supported_rule"]),
                json_paths=tuple(str(entry) for entry in row_payload["json_paths"]),
                population_rule=str(row_payload["population_rule"]),
                frontend_code_paths=tuple(str(entry) for entry in row_payload["frontend_code_paths"]),
                frontend_test_paths=tuple(str(entry) for entry in row_payload["frontend_test_paths"]),
                frontend_test_ids=tuple(str(entry) for entry in row_payload["frontend_test_ids"]),
                frontend_consumed_rule=str(row_payload["frontend_consumed_rule"]),
            )
        )

    return FrontendDataReadinessMatrix(
        selector_format=selector_format,
        chapter_deferred_rows=frozenset(chapter_rows),
        rows=tuple(parsed_rows),
    )


def _selector_status(
    *,
    selector: str,
    repo_root: Path,
    require_match: bool,
) -> tuple[bool, str]:
    relative_path, exact_substring = _parse_selector(selector)
    target_path = repo_root / relative_path
    if not target_path.exists():
        return False, f"{selector} -> missing file {relative_path}"
    if not require_match:
        return True, f"{selector} -> file exists"
    contents = target_path.read_text(encoding="utf-8")
    if exact_substring not in contents:
        return False, f"{selector} -> exact substring not found"
    return True, f"{selector} -> matched exact substring"


def _file_exists_status(*, path_text: str, repo_root: Path) -> tuple[bool, str]:
    relative_path = Path(path_text)
    target_path = repo_root / relative_path
    if not target_path.exists():
        return False, f"{path_text} -> missing file"
    return True, f"{path_text} -> file exists"


def _parse_json_path_spec(spec: str) -> tuple[str, bool, list[tuple[str, bool]]]:
    artifact_name = ""
    nested_path = ""
    root_is_list = False

    if " " in spec:
        artifact_name, _, nested_path = spec.partition(" ")
    else:
        matching_artifact = next(
            (candidate for candidate in DEFAULT_FRONTEND_DATA_READINESS_ARTIFACT_PATHS if spec.startswith(candidate)),
            None,
        )
        if matching_artifact is None:
            raise ValueError(f"invalid JSON path selector {spec!r}")
        artifact_name = matching_artifact
        nested_path = spec[len(matching_artifact) :]
        if nested_path.startswith("[]"):
            root_is_list = True
            nested_path = nested_path[2:]
            if nested_path.startswith("."):
                nested_path = nested_path[1:]

    if not artifact_name or (not nested_path and not root_is_list):
        raise ValueError(f"invalid JSON path selector {spec!r}")
    tokens: list[tuple[str, bool]] = []
    for raw_token in nested_path.split(".") if nested_path else ():
        if raw_token.endswith("[]"):
            tokens.append((raw_token[:-2], True))
        else:
            tokens.append((raw_token, False))
    return artifact_name, root_is_list, tokens


def _extract_json_values(
    payload: object,
    tokens: Sequence[tuple[str, bool]],
    *,
    root_is_list: bool = False,
) -> list[object]:
    current_values = list(payload) if root_is_list and isinstance(payload, list) else [payload]
    for key, is_list in tokens:
        next_values: list[object] = []
        for value in current_values:
            if not isinstance(value, Mapping):
                continue
            child = value.get(key)
            if is_list:
                if isinstance(child, list):
                    next_values.extend(child)
            elif child is not None:
                next_values.append(child)
        current_values = next_values
    return current_values


def _read_json_artifact(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact_summary_entry(path: Path, workflow_start_time: datetime | None) -> dict[str, object]:
    if not path.exists():
        return {
            "path": str(path),
            "mtime": None,
            "size_bytes": None,
            "fresh_after_workflow_start": False,
        }
    stat = path.stat()
    mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    fresh_after_workflow_start = workflow_start_time is not None and mtime > workflow_start_time
    return {
        "path": str(path),
        "mtime": mtime.isoformat(),
        "size_bytes": stat.st_size,
        "fresh_after_workflow_start": fresh_after_workflow_start,
    }


def _non_empty_value_count(values: Iterable[object]) -> int:
    count = 0
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value:
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        count += 1
    return count


def _segment_rows(presentation_payload: Mapping[str, object]) -> list[dict[str, object]]:
    edges = presentation_payload.get("edges")
    if not isinstance(edges, list):
        return []
    return [row for row in edges if isinstance(row, dict)]


def _repeated_player_segments(presentation_payload: Mapping[str, object]) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in _segment_rows(presentation_payload):
        payload = row.get("payload")
        if not isinstance(payload, Mapping):
            continue
        player_name = payload.get("player_name")
        asset_id = row.get("asset_id")
        start_date = row.get("start_date")
        end_date = row.get("end_date")
        if not isinstance(player_name, str) or not isinstance(asset_id, str):
            continue
        if not isinstance(start_date, str) or not isinstance(end_date, str):
            continue
        grouped[player_name].append(
            {
                "asset_id": asset_id,
                "start_date": date.fromisoformat(start_date),
                "end_date": date.fromisoformat(end_date),
            }
        )
    return grouped


def _has_leave_and_return_case(presentation_payload: Mapping[str, object]) -> tuple[bool, str]:
    for player_name, rows in _repeated_player_segments(presentation_payload).items():
        ordered = sorted(rows, key=lambda row: (row["start_date"], row["end_date"], row["asset_id"]))
        distinct_asset_ids = {str(row["asset_id"]) for row in ordered}
        if len(distinct_asset_ids) < 2:
            continue
        for left, right in zip(ordered, ordered[1:]):
            if left["asset_id"] == right["asset_id"]:
                continue
            if left["end_date"] < right["start_date"]:
                return True, f"{player_name} spans distinct asset_ids with a visible date gap"
    return False, "no repeated player display name spans distinct asset_ids with a visible date gap"


def _has_reacquired_player_case(presentation_payload: Mapping[str, object]) -> tuple[bool, str]:
    for player_name, rows in _repeated_player_segments(presentation_payload).items():
        ordered = sorted(rows, key=lambda row: (row["start_date"], row["end_date"], row["asset_id"]))
        distinct_asset_ids = {str(row["asset_id"]) for row in ordered}
        if len(distinct_asset_ids) < 2:
            continue
        first_duration = (ordered[0]["end_date"] - ordered[0]["start_date"]).days
        for row in ordered[1:]:
            later_duration = (row["end_date"] - row["start_date"]).days
            if later_duration < first_duration:
                return True, f"{player_name} has a later reacquired segment shorter than the earlier exported tenure"
    return False, "no repeated player display name shows a shorter later reacquired segment"


def _evaluate_live_population(
    *,
    row: FrontendDataReadinessRowMatrix,
    artifact_payloads: Mapping[str, object],
) -> tuple[bool, list[str]]:
    evidence: list[str] = [row.population_rule]
    extracted = {
        path_spec: _extract_json_values(artifact_payloads[artifact_name], tokens, root_is_list=root_is_list)
        for path_spec in row.json_paths
        for artifact_name, root_is_list, tokens in [_parse_json_path_spec(path_spec)]
    }
    presentation_payload = artifact_payloads["presentation-contract.json"]
    layout_payload = artifact_payloads["layout-contract.json"]
    editorial_payload = artifact_payloads["editorial-chapters.json"]

    if row.row in {"main_roster", "two_way", "future_picks"}:
        presentation_values = extracted[row.json_paths[0]]
        layout_values = extracted[row.json_paths[1]]
        presentation_count = sum(1 for value in presentation_values if value == row.row)
        layout_count = sum(1 for value in layout_values if value == row.row)
        evidence.append(
            f"presentation lane_group count={presentation_count}; layout lane_group count={layout_count}"
        )
        return presentation_count > 0 and layout_count > 0, evidence

    if row.row == "pick_protections_swaps":
        summary_values = extracted[row.json_paths[0]]
        payload_values = extracted[row.json_paths[1]]
        populated_summary_count = _non_empty_value_count(summary_values)
        populated_payload_count = sum(1 for value in payload_values if isinstance(value, dict) and value)
        evidence.append(
            "frontend-consumed pick strands with populated protection fields="
            f"{max(populated_summary_count, populated_payload_count)}"
        )
        evidence.append(
            f"non-null protection_summary count={populated_summary_count}; non-empty protection_payload count={populated_payload_count}"
        )
        return populated_summary_count > 0 or populated_payload_count > 0, evidence

    if row.row == "pick_to_player":
        link_values = extracted[row.json_paths[0]]
        drafted_player_values = extracted[row.json_paths[1]]
        pick_to_player_count = sum(1 for value in link_values if value == "pick_to_player")
        drafted_player_count = _non_empty_value_count(drafted_player_values)
        evidence.append(
            f"pick_to_player transition_links={pick_to_player_count}; drafted_player_name values={drafted_player_count}"
        )
        return pick_to_player_count > 0 and drafted_player_count > 0, evidence

    if row.row == "leave_and_return":
        found, detail = _has_leave_and_return_case(presentation_payload if isinstance(presentation_payload, Mapping) else {})
        evidence.append(detail)
        return found, evidence

    if row.row == "reacquired_players":
        found, detail = _has_reacquired_player_case(presentation_payload if isinstance(presentation_payload, Mapping) else {})
        evidence.append(detail)
        return found, evidence

    if row.row == "chapter_rows":
        editorial_count = len(editorial_payload) if isinstance(editorial_payload, list) else 0
        chapter_layout = layout_payload.get("chapter_layout") if isinstance(layout_payload, Mapping) else []
        layout_count = len(chapter_layout) if isinstance(chapter_layout, list) else 0
        evidence.append(f"editorial chapter rows={editorial_count}; chapter_layout rows={layout_count}")
        return editorial_count >= 2 and layout_count >= 2, evidence

    if row.row == "chapter_focus_fields":
        chapter_rows = layout_payload.get("chapter_layout") if isinstance(layout_payload, Mapping) else []
        populated_rows = 0
        if isinstance(chapter_rows, list):
            for chapter_row in chapter_rows:
                if not isinstance(chapter_row, Mapping):
                    continue
                has_window = bool(chapter_row.get("window_start")) and bool(chapter_row.get("window_end"))
                highlight_asset_ids = chapter_row.get("highlight_asset_ids") or []
                highlight_event_ids = chapter_row.get("highlight_event_ids") or []
                has_highlight = bool(highlight_asset_ids) or bool(highlight_event_ids)
                if has_window and (has_highlight or chapter_row.get("default_zoom") is not None):
                    populated_rows += 1
        evidence.append(f"chapter_layout rows with populated focus fields={populated_rows}")
        return populated_rows > 0, evidence

    if row.row == "identity_markers":
        image_paths = extracted[row.json_paths[0]]
        marker_variants = extracted[row.json_paths[1]]
        headshot_text_count = sum(1 for value in marker_variants if value == "headshot_text")
        text_only_count = sum(1 for value in marker_variants if value == "text_only")
        non_null_image_paths = _non_empty_value_count(image_paths)
        evidence.append(
            f"identity markers with image_path={non_null_image_paths}; headshot_text={headshot_text_count}; text_only={text_only_count}"
        )
        return non_null_image_paths > 0, evidence

    raise ValueError(f"unsupported frontend data readiness row: {row.row}")


def _evaluate_schema_support(
    *,
    row: FrontendDataReadinessRowMatrix,
    repo_root: Path,
) -> tuple[bool, list[str]]:
    evidence = [row.schema_supported_rule]
    checks = [_selector_status(selector=selector, repo_root=repo_root, require_match=True) for selector in row.schema_source_paths]
    evidence.extend(detail for _, detail in checks)
    return all(status for status, _ in checks), evidence


def _evaluate_frontend_consumption(
    *,
    row: FrontendDataReadinessRowMatrix,
    repo_root: Path,
    deferred_rows: frozenset[str],
    enforce_chapter_selector_satisfaction: bool,
) -> tuple[bool, bool, list[str]]:
    evidence = [row.frontend_consumed_rule]

    path_checks = [_file_exists_status(path_text=path_text, repo_root=repo_root) for path_text in row.frontend_test_paths]
    evidence.extend(detail for _, detail in path_checks)

    if not row.frontend_code_paths:
        evidence.append("matrix declares no direct frontend code consumer for this row")
        return False, False, evidence

    require_match = not (row.row in deferred_rows and not enforce_chapter_selector_satisfaction)
    if not require_match:
        evidence.append("chapter selector satisfaction is deferred until T3; validating selector format and file existence only")

    code_checks = [
        _selector_status(selector=selector, repo_root=repo_root, require_match=require_match)
        for selector in row.frontend_code_paths
    ]
    test_id_checks = [
        _selector_status(selector=selector, repo_root=repo_root, require_match=require_match)
        for selector in row.frontend_test_ids
    ]
    evidence.extend(detail for _, detail in code_checks)
    evidence.extend(detail for _, detail in test_id_checks)

    if not require_match:
        return False, False, evidence

    consumed = all(status for status, _ in path_checks + code_checks + test_id_checks)
    return consumed, not consumed, evidence


def _build_blocked_report(
    *,
    matrix: FrontendDataReadinessMatrix,
    artifact_summary: dict[str, object],
    workflow_start_time: datetime | None,
    wrapper_command: str,
    audit_command: str,
    prerequisites: Sequence[dict[str, object]],
    blocked_mode_reason: str,
) -> dict[str, object]:
    coverage = [
        {
            "row": row.row,
            "status": "blocked",
            "schema_supported": None,
            "live_populated": None,
            "frontend_consumed": None,
            "schema_evidence": [],
            "live_evidence": [],
            "frontend_evidence": [],
            "notes": [
                blocked_mode_reason,
                "No mixed fresh/stale readiness classification was performed.",
            ],
        }
        for row in matrix.rows
    ]
    blocked_rows = [row.row for row in matrix.rows]
    return {
        "artifact_summary": artifact_summary,
        "workflow": {
            "workflow_start_time": workflow_start_time.isoformat() if workflow_start_time is not None else None,
            "wrapper_command": wrapper_command,
            "audit_command": audit_command,
            "prerequisites": list(prerequisites),
            "freshness_gate_passed": False,
            "used_checked_in_artifacts_as_substitute": False,
            "blocked_mode_reason": blocked_mode_reason,
        },
        "coverage": coverage,
        "population_gaps": [],
        "alignment_gaps": [],
        "strengths": [],
        "blockers": [{"row": "workflow", "detail": blocked_mode_reason}],
        "overall_status": {
            "status": "blocked",
            "ready_rows": [],
            "weak_rows": [],
            "blocked_rows": blocked_rows,
            "unresolved_rows": [],
        },
    }


def _coverage_status(
    *,
    schema_supported: bool,
    live_populated: bool,
    frontend_consumed: bool,
    frontend_mismatch: bool,
) -> str:
    if not schema_supported:
        return "unresolved"
    if frontend_mismatch and live_populated:
        return "unresolved"
    if live_populated and frontend_consumed:
        return "ready"
    return "weak"


def _build_summary_markdown(report: Mapping[str, object]) -> str:
    overall = report["overall_status"]
    workflow = report["workflow"]
    lines = [
        "# Frontend Data Readiness Summary",
        "",
        f"- Overall status: {overall['status']}",
        f"- Workflow start time: {workflow['workflow_start_time']}",
        f"- Freshness gate passed: {workflow['freshness_gate_passed']}",
        "",
        "## Row Status",
    ]
    for row in report["coverage"]:
        lines.append(f"- {row['row']}: {row['status']}")
    blockers = report["blockers"]
    if blockers:
        lines.extend(["", "## Blockers"])
        for blocker in blockers:
            lines.append(f"- {blocker['row']}: {blocker['detail']}")
    population_gaps = report["population_gaps"]
    if population_gaps:
        lines.extend(["", "## Population Gaps"])
        for gap in population_gaps:
            lines.append(f"- {gap['row']}: {gap['detail']}")
    alignment_gaps = report["alignment_gaps"]
    if alignment_gaps:
        lines.extend(["", "## Alignment Gaps"])
        for gap in alignment_gaps:
            lines.append(f"- {gap['row']}: {gap['detail']}")
    strengths = report["strengths"]
    if strengths:
        lines.extend(["", "## Strengths"])
        for strength in strengths:
            lines.append(f"- {strength['row']}: {strength['detail']}")
    return "\n".join(lines) + "\n"


def write_frontend_data_readiness_outputs(
    *,
    report: Mapping[str, object],
    report_path: Path | str = DEFAULT_FRONTEND_DATA_READINESS_REPORT_PATH,
    summary_path: Path | str = DEFAULT_FRONTEND_DATA_READINESS_SUMMARY_PATH,
) -> None:
    report_path = Path(report_path)
    summary_path = Path(summary_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(yaml.safe_dump(dict(report), sort_keys=False), encoding="utf-8")
    summary_path.write_text(_build_summary_markdown(report), encoding="utf-8")


def audit_frontend_data_readiness(
    *,
    repo_root: Path | str = Path("."),
    matrix_path: Path | str = DEFAULT_FRONTEND_DATA_READINESS_MATRIX_PATH,
    presentation_path: Path | str = DEFAULT_FRONTEND_DATA_READINESS_ARTIFACT_PATHS["presentation-contract.json"],
    layout_path: Path | str = DEFAULT_FRONTEND_DATA_READINESS_ARTIFACT_PATHS["layout-contract.json"],
    editorial_chapters_path: Path | str = DEFAULT_FRONTEND_DATA_READINESS_ARTIFACT_PATHS["editorial-chapters.json"],
    report_path: Path | str = DEFAULT_FRONTEND_DATA_READINESS_REPORT_PATH,
    summary_path: Path | str = DEFAULT_FRONTEND_DATA_READINESS_SUMMARY_PATH,
    workflow_start_time: datetime | str | None = None,
    wrapper_command: str = "mise run frontend_data_readiness_audit",
    audit_command: str = "uv --cache-dir /tmp/uv-cache run python -m redesign_cli audit-frontend-data-readiness",
    prerequisites: Sequence[dict[str, object]] = (),
    blocked_mode_reason: str | None = None,
    enforce_chapter_selector_satisfaction: bool = False,
) -> FrontendDataReadinessAuditResult:
    repo_root_path = Path(repo_root)
    workflow_start_datetime = _normalize_datetime(workflow_start_time)
    matrix = load_frontend_data_readiness_matrix(matrix_path=matrix_path)

    artifact_paths = {
        "presentation-contract.json": Path(presentation_path),
        "layout-contract.json": Path(layout_path),
        "editorial-chapters.json": Path(editorial_chapters_path),
    }
    artifact_summary = {
        "presentation_contract": _artifact_summary_entry(artifact_paths["presentation-contract.json"], workflow_start_datetime),
        "layout_contract": _artifact_summary_entry(artifact_paths["layout-contract.json"], workflow_start_datetime),
        "editorial_chapters": _artifact_summary_entry(artifact_paths["editorial-chapters.json"], workflow_start_datetime),
    }

    blocking_reason = blocked_mode_reason
    if blocking_reason is None and workflow_start_datetime is None:
        blocking_reason = "workflow start time is required for freshness gating"
    if blocking_reason is None:
        missing_artifacts = [name for name, path in artifact_paths.items() if not path.exists()]
        if missing_artifacts:
            blocking_reason = f"missing required audited artifact(s): {', '.join(sorted(missing_artifacts))}"
    if blocking_reason is None:
        stale_artifacts = [
            key
            for key, summary_key in (
                ("presentation-contract.json", "presentation_contract"),
                ("layout-contract.json", "layout_contract"),
                ("editorial-chapters.json", "editorial_chapters"),
            )
            if not bool(artifact_summary[summary_key]["fresh_after_workflow_start"])
        ]
        if stale_artifacts:
            blocking_reason = (
                "freshness gate failed for audited artifact(s): "
                + ", ".join(sorted(stale_artifacts))
            )

    if blocking_reason is not None:
        report = _build_blocked_report(
            matrix=matrix,
            artifact_summary=artifact_summary,
            workflow_start_time=workflow_start_datetime,
            wrapper_command=wrapper_command,
            audit_command=audit_command,
            prerequisites=prerequisites,
            blocked_mode_reason=blocking_reason,
        )
        return FrontendDataReadinessAuditResult(
            report=report,
            report_path=Path(report_path),
            summary_path=Path(summary_path),
            exit_code=1,
        )

    artifact_payloads = {name: _read_json_artifact(path) for name, path in artifact_paths.items()}
    coverage: list[dict[str, object]] = []
    population_gaps: list[dict[str, str]] = []
    alignment_gaps: list[dict[str, str]] = []
    strengths: list[dict[str, str]] = []

    for row in matrix.rows:
        schema_supported, schema_evidence = _evaluate_schema_support(row=row, repo_root=repo_root_path)
        live_populated, live_evidence = _evaluate_live_population(row=row, artifact_payloads=artifact_payloads)
        frontend_consumed, frontend_mismatch, frontend_evidence = _evaluate_frontend_consumption(
            row=row,
            repo_root=repo_root_path,
            deferred_rows=matrix.chapter_deferred_rows,
            enforce_chapter_selector_satisfaction=enforce_chapter_selector_satisfaction,
        )
        status = _coverage_status(
            schema_supported=schema_supported,
            live_populated=live_populated,
            frontend_consumed=frontend_consumed,
            frontend_mismatch=frontend_mismatch,
        )
        notes: list[str] = []
        if row.row in matrix.chapter_deferred_rows and not enforce_chapter_selector_satisfaction:
            notes.append("Chapter frontend selector satisfaction is deferred until T3.")
        if status == "weak" and not live_populated:
            population_gaps.append({"row": row.row, "detail": live_evidence[-1]})
        if frontend_mismatch:
            alignment_gaps.append({"row": row.row, "detail": frontend_evidence[-1]})
        elif not frontend_consumed and row.frontend_code_paths:
            alignment_gaps.append({"row": row.row, "detail": frontend_evidence[-1]})
        if status == "ready":
            strengths.append({"row": row.row, "detail": live_evidence[-1]})
        coverage.append(
            {
                "row": row.row,
                "status": status,
                "schema_supported": schema_supported,
                "live_populated": live_populated,
                "frontend_consumed": frontend_consumed,
                "schema_evidence": schema_evidence,
                "live_evidence": live_evidence,
                "frontend_evidence": frontend_evidence,
                "notes": notes,
            }
        )

    ready_rows = [row["row"] for row in coverage if row["status"] == "ready"]
    weak_rows = [row["row"] for row in coverage if row["status"] == "weak"]
    unresolved_rows = [row["row"] for row in coverage if row["status"] == "unresolved"]
    overall_status = "ready"
    if unresolved_rows:
        overall_status = "unresolved"
    elif weak_rows:
        overall_status = "weak"

    report = {
        "artifact_summary": artifact_summary,
        "workflow": {
            "workflow_start_time": workflow_start_datetime.isoformat() if workflow_start_datetime is not None else None,
            "wrapper_command": wrapper_command,
            "audit_command": audit_command,
            "prerequisites": list(prerequisites),
            "freshness_gate_passed": True,
            "used_checked_in_artifacts_as_substitute": False,
            "blocked_mode_reason": None,
        },
        "coverage": coverage,
        "population_gaps": population_gaps,
        "alignment_gaps": alignment_gaps,
        "strengths": strengths,
        "blockers": [],
        "overall_status": {
            "status": overall_status,
            "ready_rows": ready_rows,
            "weak_rows": weak_rows,
            "blocked_rows": [],
            "unresolved_rows": unresolved_rows,
        },
    }
    return FrontendDataReadinessAuditResult(
        report=report,
        report_path=Path(report_path),
        summary_path=Path(summary_path),
        exit_code=0,
    )


def validate_presentation_contract(
    *,
    nodes: Iterable[TimelineNode],
    edges: Iterable[TimelineEdge],
    lanes: Iterable[AssetLane],
    canonical_events: Iterable[CanonicalEvent] = (),
) -> PresentationContractValidationReport:
    nodes_list = list(nodes)
    edges_list = list(edges)
    lanes_list = list(lanes)
    canonical_events_list = list(canonical_events)

    errors: list[str] = []
    warnings: list[str] = []

    duplicate_node_ids = [node_id for node_id, count in Counter(row.node_id for row in nodes_list).items() if count > 1]
    if duplicate_node_ids:
        errors.append(f"duplicate node_ids: {', '.join(sorted(duplicate_node_ids))}")

    duplicate_edge_ids = [edge_id for edge_id, count in Counter(row.edge_id for row in edges_list).items() if count > 1]
    if duplicate_edge_ids:
        errors.append(f"duplicate edge_ids: {', '.join(sorted(duplicate_edge_ids))}")

    duplicate_lane_ids = [lane_id for lane_id, count in Counter(row.asset_lane_id for row in lanes_list).items() if count > 1]
    if duplicate_lane_ids:
        errors.append(f"duplicate asset_lane_ids: {', '.join(sorted(duplicate_lane_ids))}")

    node_ids = {row.node_id for row in nodes_list}
    for edge in edges_list:
        if edge.source_node_id not in node_ids:
            errors.append(f"edge references unknown source_node_id: {edge.edge_id}/{edge.source_node_id}")
        if edge.target_node_id not in node_ids:
            errors.append(f"edge references unknown target_node_id: {edge.edge_id}/{edge.target_node_id}")
        if edge.end_date < edge.start_date:
            errors.append(f"edge end_date before start_date: {edge.edge_id}")
        if edge.lane_index < 0:
            errors.append(f"edge has negative lane_index: {edge.edge_id}")
        if edge.edge_type not in {"player_line", "pick_line", "transition_line"}:
            errors.append(f"invalid edge_type for {edge.edge_id}: {edge.edge_type}")
        if edge.lane_group not in {"main_roster", "two_way", "future_picks"}:
            errors.append(f"invalid lane_group for {edge.edge_id}: {edge.lane_group}")

    lane_keys = {
        (row.asset_id, row.lane_group, row.lane_index, row.effective_start_date, row.effective_end_date)
        for row in lanes_list
    }
    for edge in edges_list:
        key = (edge.asset_id, edge.lane_group, edge.lane_index, edge.start_date, edge.end_date)
        if key not in lane_keys:
            errors.append(f"edge has no matching asset lane assignment: {edge.edge_id}")

    lanes_by_index: dict[tuple[str, int], list[AssetLane]] = defaultdict(list)
    for lane in lanes_list:
        lanes_by_index[(lane.lane_group, lane.lane_index)].append(lane)
        if lane.effective_end_date < lane.effective_start_date:
            errors.append(f"lane end before start: {lane.asset_lane_id}")
        if lane.lane_index < 0:
            errors.append(f"lane has negative lane_index: {lane.asset_lane_id}")
        if lane.assignment_method != "deterministic_first_available_interval_v1":
            warnings.append(f"unexpected lane assignment method for {lane.asset_lane_id}: {lane.assignment_method}")

    for (lane_group, lane_index), grouped_lanes in lanes_by_index.items():
        ordered = sorted(grouped_lanes, key=lambda row: (row.effective_start_date, row.effective_end_date, row.asset_id, row.asset_lane_id))
        for left, right in zip(ordered, ordered[1:]):
            if left.effective_end_date > right.effective_start_date:
                errors.append(
                    f"overlapping lane usage for {lane_group}/{lane_index}: {left.asset_lane_id} overlaps {right.asset_lane_id}"
                )

    event_nodes = [row for row in nodes_list if row.event_id is not None]
    ordered_event_nodes = sorted(event_nodes, key=lambda row: (row.event_date, row.event_order, row.event_id or "", row.node_id))
    if event_nodes != ordered_event_nodes:
        errors.append("timeline event nodes are not stored in canonical order")

    if canonical_events_list:
        expected_event_order = [(row.event_id, row.event_date, row.event_order) for row in sorted(canonical_events_list, key=lambda row: (row.event_date, row.event_order, row.event_id))]
        actual_event_order = [(row.event_id, row.event_date, row.event_order) for row in ordered_event_nodes]
        if actual_event_order != expected_event_order:
            errors.append("timeline event node order does not match canonical event order")

    edges_by_asset: dict[str, list[TimelineEdge]] = defaultdict(list)
    for edge in edges_list:
        edges_by_asset[edge.asset_id].append(edge)

    for asset_id, asset_edges in edges_by_asset.items():
        ordered = sorted(asset_edges, key=lambda row: (row.start_date, row.end_date, row.edge_type, row.edge_id))
        for left, right in zip(ordered, ordered[1:]):
            if left.end_date > right.start_date and left.lane_group == right.lane_group:
                errors.append(f"same-asset overlap in lane group for {asset_id}: {left.edge_id} overlaps {right.edge_id}")
        transition_edges = [row for row in ordered if row.edge_type == "transition_line"]
        if transition_edges:
            if not any(row.edge_type == "pick_line" for row in ordered):
                errors.append(f"transition asset has no preceding pick line: {asset_id}")
            for edge in transition_edges:
                if edge.lane_group not in {"main_roster", "two_way"}:
                    errors.append(f"transition edge must use a roster lane group: {edge.edge_id}")
                if not edge.payload.get("drafted_player_id"):
                    errors.append(f"transition edge missing drafted_player_id: {edge.edge_id}")

    return PresentationContractValidationReport(
        node_count=len(nodes_list),
        edge_count=len(edges_list),
        lane_count=len(lanes_list),
        errors=errors,
        warnings=warnings,
    )


def validate_layout_contract(
    *,
    result: LayoutContractBuildResult,
    presentation_result: PresentationContractBuildResult,
    editorial_overlays: EditorialOverlayBuildResult | None = None,
    frontend_public_root: Path | str = Path("frontend/public"),
) -> LayoutContractValidationReport:
    lane_layout = list(result.lane_layout)
    event_layout = list(result.event_layout)
    label_layout = list(result.label_layout)
    chapter_layout = list(result.chapter_layout)
    presentation_edges = list(presentation_result.edges)
    presentation_nodes = [row for row in presentation_result.nodes if row.event_id is not None]
    frontend_public_root_path = Path(frontend_public_root)

    errors: list[str] = []
    warnings: list[str] = []

    if result.layout_meta.default_window_start != result.layout_meta.start_date:
        errors.append("layout_meta.default_window_start must equal layout_meta.start_date")
    if result.layout_meta.default_window_end < result.layout_meta.default_window_start:
        errors.append("layout_meta.default_window_end must be on or after layout_meta.default_window_start")
    if result.layout_meta.default_window_end > result.layout_meta.end_date:
        errors.append("layout_meta.default_window_end must be on or before layout_meta.end_date")
    if result.layout_meta.axis_strategy != {
        "minor_tick_unit": "month",
        "major_tick_unit": "season_boundary",
        "season_boundary_rule": "july_1",
    }:
        errors.append("layout_meta.axis_strategy does not match the frozen contract")
    if not result.layout_meta.minimap_segments:
        errors.append("layout_meta.minimap_segments must not be empty")
    else:
        if result.layout_meta.minimap_segments[0].start_date != result.layout_meta.start_date:
            errors.append("first minimap segment must start at layout_meta.start_date")
        if result.layout_meta.minimap_segments[-1].end_date != result.layout_meta.end_date:
            errors.append("last minimap segment must end at layout_meta.end_date")

    duplicate_segment_ids = [segment_id for segment_id, count in Counter(row.segment_id for row in lane_layout).items() if count > 1]
    if duplicate_segment_ids:
        errors.append(f"duplicate lane_layout segment_ids: {', '.join(sorted(duplicate_segment_ids))}")

    presentation_edge_by_id = {row.edge_id: row for row in presentation_edges}
    lane_by_segment_id = {row.segment_id: row for row in lane_layout}
    for row in lane_layout:
        edge = presentation_edge_by_id.get(row.segment_id)
        if edge is None:
            errors.append(f"lane_layout segment_id is missing from presentation edges: {row.segment_id}")
            continue
        if row.asset_id != edge.asset_id:
            errors.append(f"lane_layout asset_id mismatch for {row.segment_id}")
        if row.lane_group != edge.lane_group:
            errors.append(f"lane_layout lane_group mismatch for {row.segment_id}")
        if row.date_start != edge.start_date or row.date_end != edge.end_date:
            errors.append(f"lane_layout date range mismatch for {row.segment_id}")
        if row.band_slot != edge.lane_index:
            errors.append(f"lane_layout band_slot mismatch for {row.segment_id}")
        if row.entry_slot < 0 or row.exit_slot < 0:
            errors.append(f"lane_layout slot values must be non-negative: {row.segment_id}")
        if row.identity_marker.marker_variant == "headshot_text":
            if row.identity_marker.image_path is None:
                errors.append(f"headshot_text marker requires image_path: {row.segment_id}")
            elif not (frontend_public_root_path / row.identity_marker.image_path).exists():
                errors.append(f"identity_marker.image_path does not exist locally: {row.segment_id}")
        if row.identity_marker.marker_variant == "text_only" and row.identity_marker.image_path is not None:
            errors.append(f"text_only marker must not export image_path: {row.segment_id}")

    expected_segment_ids = {row.edge_id for row in presentation_edges}
    if set(lane_by_segment_id) != expected_segment_ids:
        errors.append("lane_layout segment coverage does not match presentation edges")

    duplicate_label_segments = [segment_id for segment_id, count in Counter(row.segment_id for row in label_layout).items() if count > 1]
    if duplicate_label_segments:
        errors.append(f"duplicate label_layout segment_ids: {', '.join(sorted(duplicate_label_segments))}")
    if {row.segment_id for row in label_layout} != set(lane_by_segment_id):
        errors.append("label_layout segment coverage does not match lane_layout")
    for row in label_layout:
        lane = lane_by_segment_id.get(row.segment_id)
        if lane is None:
            continue
        if row.asset_id != lane.asset_id:
            errors.append(f"label_layout asset_id mismatch for {row.segment_id}")
        if row.marker_side != "left":
            errors.append(f"label_layout marker_side must be left: {row.segment_id}")
        if row.fallback_marker_required == row.inline_label_allowed:
            errors.append(f"label_layout fallback semantics invalid for {row.segment_id}")

    presentation_event_ids = {row.event_id for row in presentation_nodes if row.event_id is not None}
    duplicate_cluster_ids = [cluster_id for cluster_id, count in Counter(row.cluster_id for row in event_layout).items() if count > 1]
    if duplicate_cluster_ids:
        errors.append(f"duplicate event_layout cluster_ids: {', '.join(sorted(duplicate_cluster_ids))}")
    for row in event_layout:
        if row.event_id not in presentation_event_ids:
            errors.append(f"event_layout event_id is missing from presentation contract: {row.event_id}")
        if row.cluster_order <= 0:
            errors.append(f"event_layout cluster_order must be positive: {row.cluster_id}")
        if row.junction_type not in {"transaction", "draft_transition", "state_boundary"}:
            errors.append(f"invalid event_layout junction_type for {row.cluster_id}: {row.junction_type}")
        if not row.member_event_ids:
            errors.append(f"event_layout member_event_ids must not be empty: {row.cluster_id}")
        for event_id in row.member_event_ids:
            if event_id not in presentation_event_ids:
                errors.append(f"event_layout member_event_id missing from presentation contract: {row.cluster_id}/{event_id}")
        for segment_id, slot in row.incoming_slots.items():
            lane = lane_by_segment_id.get(segment_id)
            if lane is None:
                errors.append(f"event_layout incoming slot references missing segment: {row.cluster_id}/{segment_id}")
            elif slot != lane.exit_slot:
                errors.append(f"event_layout incoming slot mismatch for {row.cluster_id}/{segment_id}")
        for segment_id, slot in row.outgoing_slots.items():
            lane = lane_by_segment_id.get(segment_id)
            if lane is None:
                errors.append(f"event_layout outgoing slot references missing segment: {row.cluster_id}/{segment_id}")
            elif slot != lane.entry_slot:
                errors.append(f"event_layout outgoing slot mismatch for {row.cluster_id}/{segment_id}")
        for anchor in row.transition_anchors:
            lane = lane_by_segment_id.get(anchor.segment_id)
            if lane is None:
                errors.append(f"transition_anchor references missing segment: {row.cluster_id}/{anchor.segment_id}")
                continue
            if anchor.asset_id != lane.asset_id:
                errors.append(f"transition_anchor asset mismatch for {row.cluster_id}/{anchor.segment_id}")
            if anchor.anchor_date != row.cluster_date:
                errors.append(f"transition_anchor date mismatch for {row.cluster_id}/{anchor.segment_id}")
        if row.transition_links:
            cluster_source_segments = set(row.incoming_slots)
            cluster_target_segments = set(row.outgoing_slots)
            for link in row.transition_links:
                source_lane = lane_by_segment_id.get(link.source_segment_id)
                target_lane = lane_by_segment_id.get(link.target_segment_id)
                if source_lane is None or target_lane is None:
                    errors.append(f"transition_link references missing segment: {row.cluster_id}/{link.transition_link_id}")
                    continue
                if link.source_asset_id != source_lane.asset_id:
                    errors.append(f"transition_link source asset mismatch: {row.cluster_id}/{link.transition_link_id}")
                if link.target_asset_id != target_lane.asset_id:
                    errors.append(f"transition_link target asset mismatch: {row.cluster_id}/{link.transition_link_id}")
                if link.source_segment_id not in cluster_source_segments:
                    errors.append(f"transition_link source is not incoming to cluster: {row.cluster_id}/{link.transition_link_id}")
                if link.target_segment_id not in cluster_target_segments:
                    errors.append(f"transition_link target is not outgoing from cluster: {row.cluster_id}/{link.transition_link_id}")
                if link.link_type == "same_asset" and link.source_asset_id != link.target_asset_id:
                    errors.append(f"same_asset transition_link must keep asset identity: {row.cluster_id}/{link.transition_link_id}")
                if link.link_type == "pick_to_player" and row.junction_type != "draft_transition":
                    errors.append(f"pick_to_player transition_link requires draft_transition junction: {row.cluster_id}/{link.transition_link_id}")

            expected_links = {
                (source_segment_id, target_segment_id, link_type)
                for source_segment_id, target_segment_id, _, _, link_type in _expected_transition_link_specs(
                    cluster={"junction_type": row.junction_type},
                    incoming_rows=sorted(
                        (lane_by_segment_id[segment_id] for segment_id in row.incoming_slots),
                        key=lambda lane: (lane.band_slot, lane.segment_id),
                    ),
                    outgoing_rows=sorted(
                        (lane_by_segment_id[segment_id] for segment_id in row.outgoing_slots),
                        key=lambda lane: (lane.band_slot, lane.segment_id),
                    ),
                    incoming_edges={
                        segment_id: presentation_edge_by_id[segment_id]
                        for segment_id in row.incoming_slots
                    },
                    outgoing_edges={
                        segment_id: presentation_edge_by_id[segment_id]
                        for segment_id in row.outgoing_slots
                    },
                )
            }
            actual_links = {
                (link.source_segment_id, link.target_segment_id, link.link_type)
                for link in row.transition_links
            }
            missing_links = expected_links - actual_links
            unexpected_links = actual_links - expected_links
            if missing_links:
                errors.append(f"missing transition_link coverage for cluster {row.cluster_id}")
            if unexpected_links:
                errors.append(f"unexpected transition_link coverage for cluster {row.cluster_id}")

    duplicate_chapter_ids = [chapter_id for chapter_id, count in Counter(row.story_chapter_id for row in chapter_layout).items() if count > 1]
    if duplicate_chapter_ids:
        errors.append(f"duplicate chapter_layout story_chapter_ids: {', '.join(sorted(duplicate_chapter_ids))}")
    minimap_segment_ids = {row.segment_id for row in result.layout_meta.minimap_segments}
    for row in chapter_layout:
        if row.window_end < row.window_start:
            errors.append(f"chapter_layout window_end before window_start: {row.story_chapter_id}")
        if row.window_start < result.layout_meta.start_date or row.window_end > result.layout_meta.end_date:
            errors.append(f"chapter_layout window is outside layout bounds: {row.story_chapter_id}")
        if row.minimap_anchor_id not in minimap_segment_ids:
            errors.append(f"chapter_layout minimap_anchor_id is unknown: {row.story_chapter_id}")
        if row.default_zoom is not None and not (30 <= row.default_zoom <= 180):
            errors.append(f"chapter_layout default_zoom must be between 30 and 180 days: {row.story_chapter_id}")
        if any(asset_id not in {lane.asset_id for lane in lane_layout} for asset_id in row.highlight_asset_ids):
            errors.append(f"chapter_layout highlight_asset_ids reference unknown assets: {row.story_chapter_id}")
        if any(event_id not in presentation_event_ids for event_id in row.highlight_event_ids):
            errors.append(f"chapter_layout highlight_event_ids reference unknown events: {row.story_chapter_id}")

    if editorial_overlays is not None:
        expected_chapter_ids = {row.story_chapter_id for row in editorial_overlays.story_chapters}
        if {row.story_chapter_id for row in chapter_layout} != expected_chapter_ids:
            errors.append("chapter_layout story_chapter_ids do not match editorial overlays")

    lane_groups_present = {row.lane_group for row in lane_layout}
    presentation_lane_groups = {row.lane_group for row in presentation_edges}
    if lane_groups_present != presentation_lane_groups:
        errors.append("layout lane_group coverage does not match presentation edges")

    return LayoutContractValidationReport(
        lane_layout_count=len(lane_layout),
        event_layout_count=len(event_layout),
        label_layout_count=len(label_layout),
        chapter_layout_count=len(chapter_layout),
        errors=errors,
        warnings=warnings,
    )
