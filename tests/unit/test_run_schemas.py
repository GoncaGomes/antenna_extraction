from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from antenna_ingest.orchestration.phases import complete_phase, fail_phase, start_phase
from antenna_ingest.orchestration.runs import load_run_manifest
from antenna_ingest.orchestration.schemas import (
    ArtifactReference,
    PhaseExecution,
    PhaseStatus,
    RunContext,
    RunFingerprint,
    RunManifest,
)
from antenna_ingest.utils.json_io import write_json


def test_phase_status_accepts_valid_values() -> None:
    assert PhaseStatus("pending") == PhaseStatus.PENDING
    assert PhaseStatus("running") == PhaseStatus.RUNNING
    assert PhaseStatus("completed") == PhaseStatus.COMPLETED
    assert PhaseStatus("failed") == PhaseStatus.FAILED
    assert PhaseStatus("skipped") == PhaseStatus.SKIPPED


def test_phase_status_rejects_invalid_values_through_pydantic() -> None:
    with pytest.raises(ValidationError):
        RunManifest(
            run_id="run_1",
            input_file="input/source.pdf",
            pipeline_version="0.1.0",
            phases={"run_infrastructure": "invalid"},
        )


def test_artifact_reference_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        ArtifactReference(
            name=" ",
            relative_path="input/source.pdf",
            producing_phase="run_infrastructure",
        )


def test_artifact_reference_rejects_empty_relative_path() -> None:
    with pytest.raises(ValidationError):
        ArtifactReference(
            name="source_pdf",
            relative_path=" ",
            producing_phase="run_infrastructure",
        )


def test_artifact_reference_rejects_empty_producing_phase() -> None:
    with pytest.raises(ValidationError):
        ArtifactReference(
            name="source_pdf",
            relative_path="input/source.pdf",
            producing_phase=" ",
        )


def test_run_context_validates_and_serializes_json() -> None:
    context = RunContext(
        run_id="run_1",
        document_id="document_123456789abc",
        input_sha256="a" * 64,
        input_path=Path("article.pdf"),
        run_dir=Path("runs/run_1"),
        pipeline_version="0.1.0",
        paper_id="paper-1",
    )

    dumped = context.model_dump(mode="json")

    assert dumped["input_path"] == str(Path("article.pdf"))
    assert dumped["run_dir"] == str(Path("runs/run_1"))
    assert dumped["paper_id"] == "paper-1"


def test_run_context_rejects_empty_run_id() -> None:
    with pytest.raises(ValidationError):
        RunContext(
            run_id=" ",
            input_path=Path("article.pdf"),
            run_dir=Path("runs/run_1"),
            pipeline_version="0.1.0",
        )


def test_run_manifest_validates_and_serializes_json() -> None:
    manifest = RunManifest(
        run_id="run_1",
        input_file="input/source.pdf",
        pipeline_version="0.1.0",
        phases={"run_infrastructure": PhaseStatus.COMPLETED},
        fingerprint=RunFingerprint(
            python_version="3.12.0",
            platform="test-platform",
        ),
    )

    dumped = manifest.model_dump(mode="json")

    assert dumped["phases"]["run_infrastructure"]["status"] == "completed"
    assert dumped["schema_version"] == "1.1"
    assert isinstance(dumped["created_at"], str)


def test_old_run_manifest_without_paper_id_still_loads(tmp_path) -> None:
    path = tmp_path / "manifest.json"
    write_json(
        path,
        {
            "run_id": "run_1",
            "input_file": "input/source.pdf",
            "pipeline_version": "0.1.0",
            "phase_status": {
                "run_infrastructure": "completed",
                "pending_phase": "pending",
                "failed_phase": "failed",
                "running_phase": "running",
                "skipped_phase": "skipped",
            },
            "artifacts": [
                {
                    "name": "source_pdf",
                    "relative_path": "input/source.pdf",
                    "producing_phase": "run_infrastructure",
                    "checksum": "b" * 64,
                }
            ],
        },
    )
    manifest = load_run_manifest(path)

    assert manifest.paper_id is None
    assert manifest.schema_version == "1.0"
    assert manifest.phases["run_infrastructure"].status == "completed"
    assert manifest.phases["run_infrastructure"].attempt == 1
    assert manifest.phases["pending_phase"].attempt == 0
    assert manifest.phases["failed_phase"].attempt == 1
    assert manifest.phases["running_phase"].attempt == 1
    assert manifest.phases["skipped_phase"].attempt == 1
    assert manifest.input_sha256 == "b" * 64
    assert manifest.document_id == f"document_{'b' * 12}"
    assert manifest.fingerprint is None


def test_run_manifest_add_artifact_adds_an_artifact() -> None:
    manifest = RunManifest(
        run_id="run_1",
        input_file="input/source.pdf",
        pipeline_version="0.1.0",
        phases={"run_infrastructure": PhaseStatus.COMPLETED},
    )
    artifact = ArtifactReference(
        name="source_pdf",
        relative_path="input/source.pdf",
        producing_phase="run_infrastructure",
    )

    manifest.add_artifact(artifact)

    assert manifest.artifacts == [artifact]


def test_phase_start_increments_attempt_and_clears_failure() -> None:
    manifest = _manifest()
    manifest.phases["phase"].failure_reference = "reports/failure.json"

    start_phase(manifest, "phase")

    phase = manifest.phases["phase"]
    assert phase.status == PhaseStatus.RUNNING
    assert phase.attempt == 1
    assert phase.started_at is not None
    assert phase.failure_reference is None


def test_phase_completion_records_timing() -> None:
    manifest = _manifest()
    start_phase(manifest, "phase")

    complete_phase(manifest, "phase")

    phase = manifest.phases["phase"]
    assert phase.status == PhaseStatus.COMPLETED
    assert phase.completed_at is not None
    assert phase.duration_seconds is not None
    assert phase.duration_seconds >= 0


def test_phase_failure_records_reference() -> None:
    manifest = _manifest()
    start_phase(manifest, "phase")

    fail_phase(manifest, "phase", "reports/failures/phase_attempt_001.json")

    phase = manifest.phases["phase"]
    assert phase.status == PhaseStatus.FAILED
    assert phase.failure_reference == "reports/failures/phase_attempt_001.json"
    assert phase.completed_at is not None


def test_extra_fields_are_forbidden() -> None:
    with pytest.raises(ValidationError):
        ArtifactReference(
            name="source_pdf",
            relative_path="input/source.pdf",
            producing_phase="run_infrastructure",
            extra_field=True,
        )


def _manifest() -> RunManifest:
    return RunManifest(
        run_id="run_1",
        input_file="input/source.pdf",
        pipeline_version="0.1.0",
        phases={"phase": PhaseExecution(status=PhaseStatus.PENDING)},
    )
