from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

import redesign_cli
from presentation.validate import audit_frontend_data_readiness, load_frontend_data_readiness_matrix


def _write_text(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_matrix(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {
                "artifact": "readiness_matrix",
                "feature": "frontend-data-readiness",
                "status": "draft",
                "selector_format": "relative/path::exact_substring",
                "chapter_selector_policy": {
                    "deferred_selector_satisfaction_until_task": "T3",
                    "applies_to_rows": ["chapter_rows", "chapter_focus_fields"],
                },
                "rows": rows,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _row(
    row_name: str,
    *,
    schema_source_paths: list[str],
    json_paths: list[str],
    frontend_code_paths: list[str],
    frontend_test_paths: list[str],
    frontend_test_ids: list[str],
) -> dict[str, object]:
    return {
        "row": row_name,
        "schema_source_paths": schema_source_paths,
        "schema_supported_rule": f"{row_name} schema support rule",
        "json_paths": json_paths,
        "population_rule": f"{row_name} population rule",
        "frontend_code_paths": frontend_code_paths,
        "frontend_test_paths": frontend_test_paths,
        "frontend_test_ids": frontend_test_ids,
        "frontend_consumed_rule": f"{row_name} frontend consumption rule",
    }


def _artifact_paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "presentation": tmp_path / "artifacts" / "presentation-contract.json",
        "layout": tmp_path / "artifacts" / "layout-contract.json",
        "editorial": tmp_path / "artifacts" / "editorial-chapters.json",
    }


def _write_minimal_artifacts(
    tmp_path: Path,
    *,
    presentation_payload: object,
    layout_payload: object,
    editorial_payload: object,
) -> dict[str, Path]:
    paths = _artifact_paths(tmp_path)
    _write_json(paths["presentation"], presentation_payload)
    _write_json(paths["layout"], layout_payload)
    _write_json(paths["editorial"], editorial_payload)
    return paths


def test_load_frontend_data_readiness_matrix_rejects_invalid_selectors(tmp_path: Path):
    matrix_path = tmp_path / "readiness-matrix.yaml"
    _write_matrix(
        matrix_path,
        [
            _row(
                "main_roster",
                schema_source_paths=["src/presentation/contract.py missing-separator"],
                json_paths=[
                    "presentation-contract.json edges[].lane_group",
                    "layout-contract.json lane_layout[].lane_group",
                ],
                frontend_code_paths=["frontend/src/lib/timeline.ts::main roster selector"],
                frontend_test_paths=["frontend/src/lib/timeline.test.ts"],
                frontend_test_ids=["frontend/src/lib/timeline.test.ts::main roster test"],
            )
        ],
    )

    with pytest.raises(ValueError, match="invalid selector"):
        load_frontend_data_readiness_matrix(matrix_path=matrix_path)


def test_audit_requires_exact_frontend_proof_instead_of_path_existence_only(tmp_path: Path):
    repo_root = tmp_path / "repo"
    _write_text(repo_root / "src/presentation/contract.py", "main-roster-schema\n")
    _write_text(repo_root / "frontend/src/lib/timeline.ts", "timeline file exists but lacks proof\n")
    _write_text(repo_root / "frontend/src/lib/timeline.test.ts", "timeline test file exists but lacks proof\n")

    matrix_path = tmp_path / "readiness-matrix.yaml"
    _write_matrix(
        matrix_path,
        [
            _row(
                "main_roster",
                schema_source_paths=["src/presentation/contract.py::main-roster-schema"],
                json_paths=[
                    "presentation-contract.json edges[].lane_group",
                    "layout-contract.json lane_layout[].lane_group",
                ],
                frontend_code_paths=["frontend/src/lib/timeline.ts::MAIN_ROSTER_SELECTOR"],
                frontend_test_paths=["frontend/src/lib/timeline.test.ts"],
                frontend_test_ids=["frontend/src/lib/timeline.test.ts::main roster proof"],
            )
        ],
    )
    artifacts = _write_minimal_artifacts(
        tmp_path,
        presentation_payload={"edges": [{"lane_group": "main_roster"}]},
        layout_payload={"lane_layout": [{"lane_group": "main_roster"}], "chapter_layout": []},
        editorial_payload=[],
    )

    result = audit_frontend_data_readiness(
        repo_root=repo_root,
        matrix_path=matrix_path,
        presentation_path=artifacts["presentation"],
        layout_path=artifacts["layout"],
        editorial_chapters_path=artifacts["editorial"],
        workflow_start_time=datetime.now(timezone.utc) - timedelta(minutes=1),
    )

    assert result.exit_code == 0
    assert result.report["overall_status"]["status"] == "unresolved"
    coverage = result.report["coverage"][0]
    assert coverage["row"] == "main_roster"
    assert coverage["status"] == "unresolved"
    assert coverage["schema_supported"] is True
    assert coverage["live_populated"] is True
    assert coverage["frontend_consumed"] is False
    assert any("exact substring not found" in detail for detail in coverage["frontend_evidence"])
    assert result.report["alignment_gaps"] == [
        {"row": "main_roster", "detail": coverage["frontend_evidence"][-1]}
    ]


def test_chapter_rows_defer_selector_satisfaction_until_t3(tmp_path: Path):
    repo_root = tmp_path / "repo"
    _write_text(repo_root / "src/presentation/contract.py", "chapter-schema\n")
    _write_text(repo_root / "frontend/src/lib/timeline.ts", "timeline file exists\n")
    _write_text(repo_root / "frontend/src/lib/timeline.test.ts", "timeline test file exists\n")

    matrix_path = tmp_path / "readiness-matrix.yaml"
    _write_matrix(
        matrix_path,
        [
            _row(
                "chapter_rows",
                schema_source_paths=["src/presentation/contract.py::chapter-schema"],
                json_paths=[
                    "editorial-chapters.json[].story_chapter_id",
                    "layout-contract.json chapter_layout[].story_chapter_id",
                ],
                frontend_code_paths=["frontend/src/lib/timeline.ts::CHAPTER_LAYOUT_SELECTOR"],
                frontend_test_paths=["frontend/src/lib/timeline.test.ts"],
                frontend_test_ids=["frontend/src/lib/timeline.test.ts::chapter layout proof"],
            )
        ],
    )
    artifacts = _write_minimal_artifacts(
        tmp_path,
        presentation_payload={"edges": []},
        layout_payload={
            "lane_layout": [],
            "chapter_layout": [
                {"story_chapter_id": "chapter_1"},
                {"story_chapter_id": "chapter_2"},
            ],
        },
        editorial_payload=[
            {"story_chapter_id": "chapter_1"},
            {"story_chapter_id": "chapter_2"},
        ],
    )
    workflow_start_time = datetime.now(timezone.utc) - timedelta(minutes=1)

    deferred_result = audit_frontend_data_readiness(
        repo_root=repo_root,
        matrix_path=matrix_path,
        presentation_path=artifacts["presentation"],
        layout_path=artifacts["layout"],
        editorial_chapters_path=artifacts["editorial"],
        workflow_start_time=workflow_start_time,
    )

    assert deferred_result.exit_code == 0
    deferred_coverage = deferred_result.report["coverage"][0]
    assert deferred_coverage["status"] == "weak"
    assert deferred_coverage["frontend_consumed"] is False
    assert deferred_coverage["notes"] == ["Chapter frontend selector satisfaction is deferred until T3."]
    assert any("chapter selector satisfaction is deferred until T3" in detail for detail in deferred_coverage["frontend_evidence"])
    assert not any("exact substring not found" in detail for detail in deferred_coverage["frontend_evidence"])

    enforced_result = audit_frontend_data_readiness(
        repo_root=repo_root,
        matrix_path=matrix_path,
        presentation_path=artifacts["presentation"],
        layout_path=artifacts["layout"],
        editorial_chapters_path=artifacts["editorial"],
        workflow_start_time=workflow_start_time,
        enforce_chapter_selector_satisfaction=True,
    )

    assert enforced_result.exit_code == 0
    enforced_coverage = enforced_result.report["coverage"][0]
    assert enforced_coverage["status"] == "unresolved"
    assert any("exact substring not found" in detail for detail in enforced_coverage["frontend_evidence"])


def test_audit_blocks_for_mixed_fresh_and_stale_artifacts(tmp_path: Path):
    repo_root = tmp_path / "repo"
    _write_text(repo_root / "src/presentation/contract.py", "main-roster-schema\n")
    _write_text(repo_root / "frontend/src/lib/timeline.ts", "MAIN_ROSTER_SELECTOR\n")
    _write_text(repo_root / "frontend/src/lib/timeline.test.ts", "main roster proof\n")

    matrix_path = tmp_path / "readiness-matrix.yaml"
    _write_matrix(
        matrix_path,
        [
            _row(
                "main_roster",
                schema_source_paths=["src/presentation/contract.py::main-roster-schema"],
                json_paths=[
                    "presentation-contract.json edges[].lane_group",
                    "layout-contract.json lane_layout[].lane_group",
                ],
                frontend_code_paths=["frontend/src/lib/timeline.ts::MAIN_ROSTER_SELECTOR"],
                frontend_test_paths=["frontend/src/lib/timeline.test.ts"],
                frontend_test_ids=["frontend/src/lib/timeline.test.ts::main roster proof"],
            )
        ],
    )
    artifacts = _write_minimal_artifacts(
        tmp_path,
        presentation_payload={"edges": [{"lane_group": "main_roster"}]},
        layout_payload={"lane_layout": [{"lane_group": "main_roster"}], "chapter_layout": []},
        editorial_payload=[],
    )

    workflow_start_time = datetime.now(timezone.utc)
    stale_timestamp = (workflow_start_time - timedelta(seconds=5)).timestamp()
    fresh_timestamp = (workflow_start_time + timedelta(seconds=5)).timestamp()
    os.utime(artifacts["presentation"], (fresh_timestamp, fresh_timestamp))
    os.utime(artifacts["layout"], (stale_timestamp, stale_timestamp))
    os.utime(artifacts["editorial"], (fresh_timestamp, fresh_timestamp))

    result = audit_frontend_data_readiness(
        repo_root=repo_root,
        matrix_path=matrix_path,
        presentation_path=artifacts["presentation"],
        layout_path=artifacts["layout"],
        editorial_chapters_path=artifacts["editorial"],
        workflow_start_time=workflow_start_time,
    )

    assert result.exit_code == 1
    assert result.report["overall_status"]["status"] == "blocked"
    assert result.report["population_gaps"] == []
    assert result.report["alignment_gaps"] == []
    assert result.report["strengths"] == []
    assert result.report["blockers"] == [
        {
            "row": "workflow",
            "detail": "freshness gate failed for audited artifact(s): layout-contract.json",
        }
    ]
    assert result.report["coverage"] == [
        {
            "row": "main_roster",
            "status": "blocked",
            "schema_supported": None,
            "live_populated": None,
            "frontend_consumed": None,
            "schema_evidence": [],
            "live_evidence": [],
            "frontend_evidence": [],
            "notes": [
                "freshness gate failed for audited artifact(s): layout-contract.json",
                "No mixed fresh/stale readiness classification was performed.",
            ],
        }
    ]


def test_workflow_wrapper_tracks_prerequisites_and_first_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    args = argparse.Namespace(
        presentation_path=tmp_path / "presentation-contract.json",
        layout_path=tmp_path / "layout-contract.json",
        editorial_chapters_path=tmp_path / "editorial-chapters.json",
        matrix_path=tmp_path / "readiness-matrix.yaml",
        report_path=tmp_path / "readiness-report.yaml",
        summary_path=tmp_path / "summary.md",
        wrapper_command="mise run frontend_data_readiness_audit",
        audit_command="uv --cache-dir /tmp/uv-cache run python -m redesign_cli audit-frontend-data-readiness",
        builder_version="stage8-layout-contract-v1",
        headshot_manifest_path=tmp_path / "stage8_headshot_manifest.yaml",
        frontend_public_root=tmp_path / "frontend" / "public",
        enforce_chapter_selector_satisfaction=False,
    )

    calls: dict[str, object] = {"chapter_export_called": False}

    monkeypatch.setattr(redesign_cli, "export_presentation_contract_json", lambda output_path: "{}")

    def _fail_layout_export(*args, **kwargs):
        raise RuntimeError("layout export failed")

    def _chapter_export(*args, **kwargs):
        calls["chapter_export_called"] = True
        return "[]"

    def _fake_audit_runner(**kwargs):
        calls["audit_kwargs"] = kwargs
        return 1

    monkeypatch.setattr(redesign_cli, "export_layout_contract_json", _fail_layout_export)
    monkeypatch.setattr(redesign_cli, "export_editorial_chapters_json", _chapter_export)
    monkeypatch.setattr(redesign_cli, "_run_frontend_data_readiness_audit", _fake_audit_runner)

    exit_code = redesign_cli._run_frontend_data_readiness_workflow(args)

    assert exit_code == 1
    assert calls["chapter_export_called"] is False
    audit_kwargs = calls["audit_kwargs"]
    assert audit_kwargs["command_name"] == "run-frontend-data-readiness-workflow"
    assert isinstance(audit_kwargs["workflow_start_time"], datetime)
    assert audit_kwargs["blocked_mode_reason"] == "prerequisite failed: stage8_layout_export: layout export failed"
    assert audit_kwargs["prerequisites"] == [
        {
            "name": "stage6_export",
            "command": f"uv --cache-dir /tmp/uv-cache run python -m redesign_cli export-presentation-contract --output-path {args.presentation_path}",
            "status": "success",
        },
        {
            "name": "stage8_layout_export",
            "command": "uv --cache-dir /tmp/uv-cache run python -m redesign_cli export-layout-contract "
            f"--output-path {args.layout_path} --builder-version {args.builder_version} "
            f"--headshot-manifest-path {args.headshot_manifest_path} --frontend-public-root {args.frontend_public_root}",
            "status": "failed",
            "error": "layout export failed",
        },
    ]
