from __future__ import annotations

import pytest

from antenna_ingest.orchestration.phases import (
    PhaseTransitionError,
    complete_phase,
    fail_phase,
    skip_phase,
    start_phase,
)
from antenna_ingest.orchestration.schemas import (
    RUN_PHASES,
    PhaseExecution,
    PhaseStatus,
    RunFingerprint,
    RunManifest,
)


def test_start_and_complete_phase_record_attempt_and_timing() -> None:
    manifest = _manifest()

    started = start_phase(
        manifest,
        "page_rendering",
        input_artifact_names=["source_pdf"],
    )
    completed = complete_phase(
        manifest,
        "page_rendering",
        output_artifact_names=["rendered_pages", "render_report"],
    )

    assert started is completed
    assert completed.status == PhaseStatus.COMPLETED
    assert completed.attempt == 1
    assert completed.started_at is not None
    assert completed.completed_at is not None
    assert completed.duration_seconds is not None
    assert completed.input_artifact_names == ["source_pdf"]
    assert completed.output_artifact_names == ["rendered_pages", "render_report"]


def test_only_one_phase_can_run() -> None:
    manifest = _manifest()
    start_phase(manifest, "page_rendering")

    with pytest.raises(PhaseTransitionError, match="is running"):
        start_phase(manifest, "paper_extraction")


def test_failed_phase_can_be_retried() -> None:
    manifest = _manifest()
    start_phase(manifest, "page_rendering")
    fail_phase(manifest, "page_rendering", "reports/failures/render.json")

    phase = start_phase(manifest, "page_rendering")

    assert phase.status == PhaseStatus.RUNNING
    assert phase.attempt == 2
    assert phase.failure_reference is None


def test_completed_phase_restart_requires_explicit_permission() -> None:
    manifest = _manifest()
    start_phase(manifest, "page_rendering")
    complete_phase(manifest, "page_rendering")

    with pytest.raises(PhaseTransitionError, match="from status 'completed'"):
        start_phase(manifest, "page_rendering")

    phase = start_phase(
        manifest,
        "page_rendering",
        allow_completed_restart=True,
    )
    assert phase.attempt == 2


def test_pending_phase_can_be_skipped() -> None:
    phase = skip_phase(_manifest(), "paper_extraction")

    assert phase.status == PhaseStatus.SKIPPED
    assert phase.completed_at is not None


def test_unknown_phase_is_rejected() -> None:
    with pytest.raises(PhaseTransitionError, match="unknown phase"):
        start_phase(_manifest(), "unknown")


def _manifest() -> RunManifest:
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
        phases={
            name: PhaseExecution(
                status=(
                    PhaseStatus.COMPLETED
                    if name == "run_initialization"
                    else PhaseStatus.PENDING
                )
            )
            for name in RUN_PHASES
        },
    )
