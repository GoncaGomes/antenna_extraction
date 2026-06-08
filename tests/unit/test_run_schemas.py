from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from antenna_ingest.orchestration.schemas import (
    ArtifactReference,
    PhaseStatus,
    RunContext,
    RunManifest,
)


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
            phase_status={"run_infrastructure": "invalid"},
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
        phase_status={"run_infrastructure": PhaseStatus.COMPLETED},
    )

    dumped = manifest.model_dump(mode="json")

    assert dumped["phase_status"]["run_infrastructure"] == "completed"
    assert isinstance(dumped["created_at"], str)


def test_old_run_manifest_without_paper_id_still_validates() -> None:
    manifest = RunManifest.model_validate(
        {
            "run_id": "run_1",
            "input_file": "input/source.pdf",
            "pipeline_version": "0.1.0",
            "phase_status": {"run_infrastructure": "completed"},
        }
    )

    assert manifest.paper_id is None


def test_run_manifest_add_artifact_adds_an_artifact() -> None:
    manifest = RunManifest(
        run_id="run_1",
        input_file="input/source.pdf",
        pipeline_version="0.1.0",
        phase_status={"run_infrastructure": PhaseStatus.COMPLETED},
    )
    artifact = ArtifactReference(
        name="source_pdf",
        relative_path="input/source.pdf",
        producing_phase="run_infrastructure",
    )

    manifest.add_artifact(artifact)

    assert manifest.artifacts == [artifact]


def test_extra_fields_are_forbidden() -> None:
    with pytest.raises(ValidationError):
        ArtifactReference(
            name="source_pdf",
            relative_path="input/source.pdf",
            producing_phase="run_infrastructure",
            extra_field=True,
        )
