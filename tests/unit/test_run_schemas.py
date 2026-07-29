from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from antenna_ingest.orchestration.schemas import (
    MANIFEST_SCHEMA_VERSION,
    RUN_PHASES,
    ArtifactReference,
    PhaseExecution,
    PhaseStatus,
    RunContext,
    RunFingerprint,
    RunManifest,
)


def test_phase_status_values_are_exact() -> None:
    assert [status.value for status in PhaseStatus] == [
        "pending",
        "running",
        "completed",
        "failed",
        "skipped",
    ]
    with pytest.raises(ValidationError):
        PhaseExecution(status="invalid")


@pytest.mark.parametrize("field", ["name", "relative_path", "producing_phase"])
def test_artifact_reference_rejects_empty_required_strings(field) -> None:
    values = {
        "name": "source_pdf",
        "relative_path": "input/source.pdf",
        "producing_phase": "run_initialization",
    }
    values[field] = " "

    with pytest.raises(ValidationError):
        ArtifactReference(**values)


def test_run_context_serializes_paths() -> None:
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


def test_run_manifest_has_one_record_per_ordered_phase() -> None:
    manifest = _manifest()
    dumped = manifest.model_dump(mode="json")

    assert dumped["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert tuple(dumped["phases"]) == RUN_PHASES
    assert dumped["phases"]["run_initialization"]["status"] == "completed"
    assert isinstance(dumped["created_at"], str)


def test_run_manifest_rejects_wrong_phase_set() -> None:
    values = _manifest().model_dump()
    values["phases"].pop("output_validation")

    with pytest.raises(ValidationError, match="ordered pipeline phase set"):
        RunManifest.model_validate(values)


def test_run_manifest_rejects_other_schema_versions() -> None:
    values = _manifest().model_dump()
    values["schema_version"] = "2.0"

    with pytest.raises(ValidationError):
        RunManifest.model_validate(values)


def test_run_manifest_rejects_multiple_running_phases() -> None:
    phases = _phases()
    phases["page_rendering"].status = PhaseStatus.RUNNING
    phases["paper_extraction"].status = PhaseStatus.RUNNING

    with pytest.raises(ValidationError, match="only one phase"):
        _manifest(phases=phases)


def test_phase_execution_preserves_minimal_metadata() -> None:
    execution = PhaseExecution(
        status=PhaseStatus.PENDING,
        prompt_hash="prompt_hash",
        schema_hash="schema_hash",
        model_role="document_extractor",
        input_artifact_names=["rendered_pages"],
        output_artifact_names=["paper_extraction"],
    )

    dumped = execution.model_dump(mode="json")

    assert dumped["model_role"] == "document_extractor"
    assert dumped["input_artifact_names"] == ["rendered_pages"]
    assert dumped["output_artifact_names"] == ["paper_extraction"]
    assert set(dumped) == {
        "status",
        "attempt",
        "started_at",
        "completed_at",
        "duration_seconds",
        "model_role",
        "input_artifact_names",
        "output_artifact_names",
        "failure_reference",
        "prompt_hash",
        "schema_hash",
    }


def test_strict_models_forbid_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ArtifactReference(
            name="source_pdf",
            relative_path="input/source.pdf",
            producing_phase="run_initialization",
            extra_field=True,
        )


def _phases() -> dict[str, PhaseExecution]:
    return {
        name: PhaseExecution(
            status=(
                PhaseStatus.COMPLETED
                if name == "run_initialization"
                else PhaseStatus.PENDING
            )
        )
        for name in RUN_PHASES
    }


def _manifest(
    *,
    phases: dict[str, PhaseExecution] | None = None,
) -> RunManifest:
    return RunManifest(
        run_id="run_1",
        input_file="input/source.pdf",
        document_id="document_123456789abc",
        input_sha256="a" * 64,
        pipeline_version="0.1.0",
        fingerprint=RunFingerprint(
            python_version="3.12.0",
            platform="test-platform",
        ),
        phases=phases or _phases(),
    )
