from __future__ import annotations

from datetime import datetime, timezone

from antenna_ingest.orchestration.schemas import (
    PhaseExecution,
    PhaseStatus,
    RunManifest,
)


def start_phase(manifest: RunManifest, phase_name: str) -> None:
    phase = manifest.phases.setdefault(
        phase_name,
        PhaseExecution(status=PhaseStatus.PENDING),
    )
    phase.attempt += 1
    phase.status = PhaseStatus.RUNNING
    phase.started_at = datetime.now(timezone.utc)
    phase.completed_at = None
    phase.duration_seconds = None
    phase.failure_reference = None


def complete_phase(manifest: RunManifest, phase_name: str) -> None:
    phase = manifest.phases.setdefault(
        phase_name,
        PhaseExecution(status=PhaseStatus.PENDING),
    )
    completed_at = datetime.now(timezone.utc)
    phase.status = PhaseStatus.COMPLETED
    phase.completed_at = completed_at
    phase.duration_seconds = _duration_seconds(phase.started_at, completed_at)
    phase.failure_reference = None


def fail_phase(
    manifest: RunManifest,
    phase_name: str,
    failure_reference: str | None,
) -> None:
    phase = manifest.phases.setdefault(
        phase_name,
        PhaseExecution(status=PhaseStatus.PENDING),
    )
    completed_at = datetime.now(timezone.utc)
    phase.status = PhaseStatus.FAILED
    phase.completed_at = completed_at
    phase.duration_seconds = _duration_seconds(phase.started_at, completed_at)
    phase.failure_reference = failure_reference


def _duration_seconds(
    started_at: datetime | None,
    completed_at: datetime,
) -> float | None:
    if started_at is None:
        return None
    return max((completed_at - started_at).total_seconds(), 0.0)
