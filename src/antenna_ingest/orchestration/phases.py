from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from antenna_ingest.orchestration.pipeline_spec import (
    is_pipeline_phase,
    phase_prerequisites,
    validate_phase_scope,
)
from antenna_ingest.orchestration.schemas import (
    PhaseExecution,
    PhaseStatus,
    RunManifest,
)


class PhaseTransitionError(ValueError):
    pass


class PhasePrerequisiteError(ValueError):
    pass


def create_phase_execution(
    manifest: RunManifest,
    phase_name: str,
    *,
    design_id: str | None = None,
) -> PhaseExecution:
    design_id = _validated_scope(phase_name, design_id)
    executions = manifest.phases.setdefault(phase_name, [])
    if any(execution.scope_design_id == design_id for execution in executions):
        raise PhaseTransitionError(
            f"phase {phase_name!r} already has an execution for "
            f"design scope {design_id!r}"
        )
    execution = PhaseExecution(
        status=PhaseStatus.PENDING,
        scope_design_id=design_id,
    )
    executions.append(execution)
    return execution


def get_phase_execution(
    manifest: RunManifest,
    phase_name: str,
    *,
    design_id: str | None = None,
) -> PhaseExecution:
    design_id = _validated_scope(phase_name, design_id)
    matches = [
        execution
        for execution in manifest.phases.get(phase_name, [])
        if execution.scope_design_id == design_id
    ]
    if not matches:
        raise PhaseTransitionError(
            f"phase {phase_name!r} has no execution for design scope {design_id!r}"
        )
    if len(matches) > 1:
        raise PhaseTransitionError(
            f"phase {phase_name!r} has duplicate executions for "
            f"design scope {design_id!r}"
        )
    return matches[0]


def start_phase(
    manifest: RunManifest,
    phase_name: str,
    *,
    design_id: str | None = None,
    run_dir: Path | None = None,
    validate_prerequisites: bool = True,
    allow_completed_restart: bool = False,
) -> PhaseExecution:
    design_id = _validated_scope(phase_name, design_id)
    phase = _get_or_create_execution(manifest, phase_name, design_id)
    _ensure_no_other_running_phase(manifest, phase)
    _ensure_can_transition(
        phase,
        phase_name,
        "start",
        allowed={PhaseStatus.PENDING, PhaseStatus.FAILED, PhaseStatus.BLOCKED},
        allow_completed_restart=(
            allow_completed_restart or not is_pipeline_phase(phase_name)
        ),
    )
    if validate_prerequisites:
        validate_phase_prerequisites(manifest, phase_name, run_dir)

    phase.attempt += 1
    phase.status = PhaseStatus.RUNNING
    phase.started_at = datetime.now(timezone.utc)
    phase.completed_at = None
    phase.duration_seconds = None
    phase.failure_reference = None
    phase.blocked_reason = None
    phase.skipped_reason = None
    phase.input_artifact_names = list(phase_prerequisites(phase_name))
    return phase


def complete_phase(
    manifest: RunManifest,
    phase_name: str,
    *,
    design_id: str | None = None,
) -> PhaseExecution:
    phase = get_phase_execution(manifest, phase_name, design_id=design_id)
    _ensure_can_transition(
        phase,
        phase_name,
        "complete",
        allowed={PhaseStatus.RUNNING},
    )
    _finish_execution(phase, PhaseStatus.COMPLETED)
    phase.failure_reference = None
    return phase


def fail_phase(
    manifest: RunManifest,
    phase_name: str,
    failure_reference: str | None,
    *,
    design_id: str | None = None,
) -> PhaseExecution:
    phase = get_phase_execution(manifest, phase_name, design_id=design_id)
    _ensure_can_transition(
        phase,
        phase_name,
        "fail",
        allowed={PhaseStatus.RUNNING},
    )
    _finish_execution(phase, PhaseStatus.FAILED)
    phase.failure_reference = failure_reference
    return phase


def block_phase(
    manifest: RunManifest,
    phase_name: str,
    reason: str,
    *,
    design_id: str | None = None,
) -> PhaseExecution:
    cleaned_reason = _clean_reason(reason, "blocked")
    phase = _get_or_create_execution(
        manifest,
        phase_name,
        _validated_scope(phase_name, design_id),
    )
    _ensure_can_transition(
        phase,
        phase_name,
        "block",
        allowed={PhaseStatus.PENDING, PhaseStatus.RUNNING},
    )
    _finish_execution(phase, PhaseStatus.BLOCKED)
    phase.blocked_reason = cleaned_reason
    phase.skipped_reason = None
    return phase


def skip_phase(
    manifest: RunManifest,
    phase_name: str,
    reason: str,
    *,
    design_id: str | None = None,
) -> PhaseExecution:
    cleaned_reason = _clean_reason(reason, "skipped")
    phase = _get_or_create_execution(
        manifest,
        phase_name,
        _validated_scope(phase_name, design_id),
    )
    _ensure_can_transition(
        phase,
        phase_name,
        "skip",
        allowed={PhaseStatus.PENDING},
    )
    _finish_execution(phase, PhaseStatus.SKIPPED)
    phase.skipped_reason = cleaned_reason
    phase.blocked_reason = None
    return phase


def validate_phase_prerequisites(
    manifest: RunManifest,
    phase_name: str,
    run_dir: Path | None,
) -> None:
    required_names = phase_prerequisites(phase_name)
    if not required_names:
        return

    artifacts_by_name = {artifact.name: artifact for artifact in manifest.artifacts}
    missing_names = [
        name for name in required_names if name not in artifacts_by_name
    ]
    if missing_names:
        raise PhasePrerequisiteError(
            f"phase {phase_name!r} is missing required artifacts: "
            f"{', '.join(missing_names)}"
        )
    if run_dir is None:
        raise PhasePrerequisiteError(
            f"run_dir is required to validate prerequisites for phase "
            f"{phase_name!r}"
        )

    root = Path(run_dir).resolve()
    missing_paths: list[str] = []
    for name in required_names:
        artifact = artifacts_by_name[name]
        relative_path = Path(artifact.relative_path)
        if relative_path.is_absolute():
            raise PhasePrerequisiteError(
                f"artifact {name!r} path must be relative to the run directory"
            )
        artifact_path = (root / relative_path).resolve()
        if not artifact_path.is_relative_to(root):
            raise PhasePrerequisiteError(
                f"artifact {name!r} path escapes the run directory"
            )
        if not artifact_path.exists():
            missing_paths.append(artifact.relative_path)

    if missing_paths:
        raise PhasePrerequisiteError(
            f"phase {phase_name!r} has missing prerequisite paths: "
            f"{', '.join(missing_paths)}"
        )


def _validated_scope(phase_name: str, design_id: str | None) -> str | None:
    cleaned_design_id = None
    if design_id is not None:
        cleaned_design_id = " ".join(design_id.split())
        if not cleaned_design_id:
            raise PhaseTransitionError("design_id must not be empty")

    if is_pipeline_phase(phase_name):
        try:
            validate_phase_scope(phase_name, cleaned_design_id)
        except ValueError as error:
            raise PhaseTransitionError(str(error)) from error
    return cleaned_design_id


def _get_or_create_execution(
    manifest: RunManifest,
    phase_name: str,
    design_id: str | None,
) -> PhaseExecution:
    matches = [
        execution
        for execution in manifest.phases.get(phase_name, [])
        if execution.scope_design_id == design_id
    ]
    if matches:
        if len(matches) > 1:
            raise PhaseTransitionError(
                f"phase {phase_name!r} has duplicate executions for "
                f"design scope {design_id!r}"
            )
        return matches[0]
    return create_phase_execution(manifest, phase_name, design_id=design_id)


def _ensure_no_other_running_phase(
    manifest: RunManifest,
    selected_phase: PhaseExecution,
) -> None:
    for phase_name, executions in manifest.phases.items():
        for execution in executions:
            if execution is not selected_phase and execution.status == PhaseStatus.RUNNING:
                raise PhaseTransitionError(
                    f"cannot start a phase while {phase_name!r} is running"
                )


def _ensure_can_transition(
    phase: PhaseExecution,
    phase_name: str,
    action: str,
    *,
    allowed: set[PhaseStatus],
    allow_completed_restart: bool = False,
) -> None:
    if allow_completed_restart and action == "start":
        allowed = allowed | {PhaseStatus.COMPLETED, PhaseStatus.SKIPPED}
    if phase.status not in allowed:
        expected = ", ".join(sorted(status.value for status in allowed))
        raise PhaseTransitionError(
            f"cannot {action} phase {phase_name!r} from status "
            f"{phase.status.value!r}; expected one of: {expected}"
        )


def _finish_execution(
    phase: PhaseExecution,
    status: PhaseStatus,
) -> None:
    completed_at = datetime.now(timezone.utc)
    phase.status = status
    phase.completed_at = completed_at
    phase.duration_seconds = _duration_seconds(phase.started_at, completed_at)


def _clean_reason(reason: str, status_name: str) -> str:
    cleaned = " ".join(reason.split())
    if not cleaned:
        raise PhaseTransitionError(f"{status_name} reason must not be empty")
    return cleaned


def _duration_seconds(
    started_at: datetime | None,
    completed_at: datetime,
) -> float | None:
    if started_at is None:
        return None
    return max((completed_at - started_at).total_seconds(), 0.0)
