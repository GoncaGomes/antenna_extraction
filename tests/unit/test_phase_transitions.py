from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from antenna_ingest.orchestration.phases import (
    PhasePrerequisiteError,
    PhaseTransitionError,
    block_phase,
    complete_phase,
    create_phase_execution,
    fail_phase,
    skip_phase,
    start_phase,
)
from antenna_ingest.orchestration.pipeline_spec import (
    GLOBAL_PHASES,
    PER_DESIGN_PHASES,
    PIPELINE_PHASES,
)
from antenna_ingest.orchestration.runs import create_run, load_run_manifest
from antenna_ingest.orchestration.schemas import (
    ArtifactReference,
    PhaseExecution,
    PhaseStatus,
    RunManifest,
)
from antenna_ingest.utils.json_io import write_json


def test_new_run_has_global_and_empty_per_design_executions(tmp_path) -> None:
    manifest, _ = _new_run(tmp_path)

    assert list(manifest.phases) == PIPELINE_PHASES
    for phase_name in GLOBAL_PHASES:
        assert len(manifest.phases[phase_name]) == 1
        assert manifest.phases[phase_name][0].scope_design_id is None
    for phase_name in PER_DESIGN_PHASES:
        assert manifest.phases[phase_name] == []


def test_two_designs_get_distinct_executions_and_run_sequentially(tmp_path) -> None:
    manifest, run_dir = _new_run(tmp_path)
    _add_file_artifact(manifest, run_dir, "design_resolution")
    first = create_phase_execution(
        manifest,
        "visual_task_planning",
        design_id="design_a",
    )
    second = create_phase_execution(
        manifest,
        "visual_task_planning",
        design_id="design_b",
    )

    start_phase(
        manifest,
        "visual_task_planning",
        design_id="design_a",
        run_dir=run_dir,
    )
    with pytest.raises(PhaseTransitionError, match="is running"):
        start_phase(
            manifest,
            "visual_task_planning",
            design_id="design_b",
            run_dir=run_dir,
        )

    complete_phase(manifest, "visual_task_planning", design_id="design_a")
    start_phase(
        manifest,
        "visual_task_planning",
        design_id="design_b",
        run_dir=run_dir,
    )

    assert first.status == PhaseStatus.COMPLETED
    assert second.status == PhaseStatus.RUNNING


def test_duplicate_phase_design_execution_is_rejected(tmp_path) -> None:
    manifest, _ = _new_run(tmp_path)
    create_phase_execution(manifest, "visual_analysis", design_id="design_a")

    with pytest.raises(PhaseTransitionError, match="already has an execution"):
        create_phase_execution(manifest, "visual_analysis", design_id="design_a")


def test_phase_scope_rules_are_enforced(tmp_path) -> None:
    manifest, _ = _new_run(tmp_path)

    with pytest.raises(PhaseTransitionError, match="cannot have a design scope"):
        create_phase_execution(
            manifest,
            "page_asset_rendering",
            design_id="design_a",
        )
    with pytest.raises(PhaseTransitionError, match="requires a design_id"):
        create_phase_execution(manifest, "visual_analysis")


def test_manifest_rejects_more_than_one_running_execution() -> None:
    with pytest.raises(ValidationError, match="only one phase execution"):
        RunManifest(
            run_id="run_1",
            input_file="input/article.pdf",
            pipeline_version="0.1.0",
            phases={
                "legacy_a": [PhaseExecution(status=PhaseStatus.RUNNING)],
                "legacy_b": [PhaseExecution(status=PhaseStatus.RUNNING)],
            },
        )


def test_phase_start_requires_registered_artifact(tmp_path) -> None:
    manifest, run_dir = _new_run(tmp_path)
    manifest.artifacts.clear()

    with pytest.raises(PhasePrerequisiteError, match="source_pdf"):
        start_phase(manifest, "page_asset_rendering", run_dir=run_dir)


def test_phase_start_requires_artifact_path_to_exist(tmp_path) -> None:
    manifest, run_dir = _new_run(tmp_path)
    manifest.artifacts[0].relative_path = "input/missing.pdf"

    with pytest.raises(PhasePrerequisiteError, match="input/missing.pdf"):
        start_phase(manifest, "page_asset_rendering", run_dir=run_dir)


def test_blocked_and_skipped_transitions_record_reasons(tmp_path) -> None:
    manifest, _ = _new_run(tmp_path)

    blocked = block_phase(
        manifest,
        "visual_analysis",
        "  selected design remains ambiguous  ",
        design_id="design_a",
    )
    skipped = skip_phase(
        manifest,
        "architecture_finalization",
        "verification accepted without corrections",
        design_id="design_a",
    )

    assert blocked.status == PhaseStatus.BLOCKED
    assert blocked.blocked_reason == "selected design remains ambiguous"
    assert skipped.status == PhaseStatus.SKIPPED
    assert skipped.skipped_reason == "verification accepted without corrections"


@pytest.mark.parametrize("transition", [block_phase, skip_phase])
def test_blocked_and_skipped_transitions_require_reason(
    tmp_path,
    transition,
) -> None:
    manifest, _ = _new_run(tmp_path)

    with pytest.raises(PhaseTransitionError, match="reason must not be empty"):
        transition(
            manifest,
            "visual_analysis",
            " ",
            design_id="design_a",
        )


def test_failure_can_be_retried_and_increments_attempt(tmp_path) -> None:
    manifest, run_dir = _new_run(tmp_path)
    start_phase(manifest, "page_asset_rendering", run_dir=run_dir)
    fail_phase(manifest, "page_asset_rendering", "reports/failure.json")

    phase = start_phase(manifest, "page_asset_rendering", run_dir=run_dir)

    assert phase.status == PhaseStatus.RUNNING
    assert phase.attempt == 2
    assert phase.failure_reference is None


def test_invalid_transition_reports_phase_and_status(tmp_path) -> None:
    manifest, _ = _new_run(tmp_path)

    with pytest.raises(
        PhaseTransitionError,
        match="cannot complete phase 'page_asset_rendering' from status 'pending'",
    ):
        complete_phase(manifest, "page_asset_rendering")


def test_current_single_execution_manifest_loads_without_rewrite(tmp_path) -> None:
    path = tmp_path / "manifest.json"
    write_json(
        path,
        {
            "schema_version": "1.1",
            "run_id": "run_legacy",
            "input_file": "input/article.pdf",
            "pipeline_version": "0.1.0",
            "phases": {
                "unknown_legacy_phase": {
                    "status": "completed",
                    "attempt": 1,
                }
            },
        },
    )
    original = path.read_bytes()

    manifest = load_run_manifest(path)

    assert path.read_bytes() == original
    assert list(manifest.phases) == ["unknown_legacy_phase"]
    assert manifest.phases["unknown_legacy_phase"][0].status == "completed"


def test_new_execution_list_manifest_loads(tmp_path) -> None:
    path = tmp_path / "manifest.json"
    write_json(
        path,
        {
            "schema_version": "2.0",
            "run_id": "run_new",
            "input_file": "input/article.pdf",
            "pipeline_version": "0.1.0",
            "phases": {
                "visual_analysis": [
                    {
                        "status": "pending",
                        "scope_design_id": "design_a",
                    },
                    {
                        "status": "pending",
                        "scope_design_id": "design_b",
                    },
                ]
            },
        },
    )

    manifest = load_run_manifest(path)

    assert [
        execution.scope_design_id
        for execution in manifest.phases["visual_analysis"]
    ] == ["design_a", "design_b"]


def _new_run(tmp_path: Path) -> tuple[RunManifest, Path]:
    article = tmp_path / "article.pdf"
    article.write_bytes(b"%PDF-1.4\n%test\n")
    context = create_run(article, runs_root=tmp_path / "runs")
    return load_run_manifest(context.run_dir / "manifest.json"), context.run_dir


def _add_file_artifact(
    manifest: RunManifest,
    run_dir: Path,
    name: str,
) -> None:
    relative_path = Path("reports") / f"{name}.json"
    path = run_dir / relative_path
    path.write_text("{}", encoding="utf-8")
    manifest.add_artifact(
        ArtifactReference(
            name=name,
            relative_path=relative_path.as_posix(),
            producing_phase="test",
        )
    )
