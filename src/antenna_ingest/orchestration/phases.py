from __future__ import annotations

from datetime import datetime, timezone

from antenna_ingest.orchestration.schemas import (
    PhaseExecution,
    PhaseStatus,
    RunManifest,
)


class PhaseTransitionError(ValueError):
    pass


def get_phase(manifest: RunManifest, phase_name: str) -> PhaseExecution:
    try:
        return manifest.phases[phase_name]
    except KeyError as error:
        raise PhaseTransitionError(f"unknown phase: {phase_name!r}") from error


def start_phase(
    manifest: RunManifest,
    phase_name: str,
    *,
    allow_completed_restart: bool = False,
    model_role: str | None = None,
    input_artifact_names: list[str] | None = None,
    prompt_hash: str | None = None,
    schema_hash: str | None = None,
) -> PhaseExecution:
    phase = get_phase(manifest, phase_name)
    _ensure_no_other_running_phase(manifest, phase)
    allowed = {PhaseStatus.PENDING, PhaseStatus.FAILED}
    if allow_completed_restart:
        allowed.add(PhaseStatus.COMPLETED)
    _ensure_can_transition(phase, phase_name, "start", allowed)

    phase.attempt += 1
    phase.status = PhaseStatus.RUNNING
    phase.started_at = datetime.now(timezone.utc)
    phase.completed_at = None
    phase.duration_seconds = None
    phase.model_role = model_role
    phase.input_artifact_names = list(input_artifact_names or [])
    phase.output_artifact_names = []
    phase.failure_reference = None
    phase.prompt_hash = prompt_hash
    phase.schema_hash = schema_hash
    return phase


def complete_phase(
    manifest: RunManifest,
    phase_name: str,
    *,
    output_artifact_names: list[str] | None = None,
) -> PhaseExecution:
    phase = get_phase(manifest, phase_name)
    _ensure_can_transition(
        phase,
        phase_name,
        "complete",
        {PhaseStatus.RUNNING},
    )
    _finish_phase(phase, PhaseStatus.COMPLETED)
    phase.output_artifact_names = list(output_artifact_names or [])
    return phase


def fail_phase(
    manifest: RunManifest,
    phase_name: str,
    failure_reference: str | None,
) -> PhaseExecution:
    phase = get_phase(manifest, phase_name)
    _ensure_can_transition(
        phase,
        phase_name,
        "fail",
        {PhaseStatus.RUNNING},
    )
    _finish_phase(phase, PhaseStatus.FAILED)
    phase.failure_reference = failure_reference
    return phase


def skip_phase(manifest: RunManifest, phase_name: str) -> PhaseExecution:
    phase = get_phase(manifest, phase_name)
    _ensure_can_transition(
        phase,
        phase_name,
        "skip",
        {PhaseStatus.PENDING},
    )
    _finish_phase(phase, PhaseStatus.SKIPPED)
    return phase


def _ensure_no_other_running_phase(
    manifest: RunManifest,
    selected_phase: PhaseExecution,
) -> None:
    for phase_name, phase in manifest.phases.items():
        if phase is not selected_phase and phase.status == PhaseStatus.RUNNING:
            raise PhaseTransitionError(
                f"cannot start a phase while {phase_name!r} is running"
            )


def _ensure_can_transition(
    phase: PhaseExecution,
    phase_name: str,
    action: str,
    allowed: set[PhaseStatus],
) -> None:
    if phase.status not in allowed:
        expected = ", ".join(sorted(status.value for status in allowed))
        raise PhaseTransitionError(
            f"cannot {action} phase {phase_name!r} from status "
            f"{phase.status.value!r}; expected one of: {expected}"
        )


def _finish_phase(phase: PhaseExecution, status: PhaseStatus) -> None:
    completed_at = datetime.now(timezone.utc)
    phase.status = status
    phase.completed_at = completed_at
    phase.duration_seconds = _duration_seconds(phase.started_at, completed_at)


def _duration_seconds(
    started_at: datetime | None,
    completed_at: datetime,
) -> float | None:
    if started_at is None:
        return None
    return max((completed_at - started_at).total_seconds(), 0.0)
