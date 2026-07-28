from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from antenna_ingest.orchestration.pipeline_spec import (
    is_global_phase,
    is_per_design_phase,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PhaseStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class RunFingerprint(StrictModel):
    git_commit: str | None = None
    git_dirty: bool | None = None
    python_version: str
    platform: str
    pyproject_sha256: str | None = None
    lockfile_sha256: str | None = None


class PhaseExecution(StrictModel):
    status: PhaseStatus
    scope_design_id: str | None = None
    attempt: int = Field(default=0, ge=0)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    failure_reference: str | None = None
    blocked_reason: str | None = None
    skipped_reason: str | None = None
    prompt_hash: str | None = None
    schema_hash: str | None = None
    model_role: str | None = None
    invocation_ids: list[str] = Field(default_factory=list)
    input_artifact_names: list[str] = Field(default_factory=list)
    output_artifact_names: list[str] = Field(default_factory=list)

    @field_validator(
        "scope_design_id",
        "failure_reference",
        "blocked_reason",
        "skipped_reason",
        "prompt_hash",
        "schema_hash",
        "model_role",
    )
    @classmethod
    def validate_optional_non_empty_string(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("field must not be empty when provided")
        return cleaned

    @field_validator(
        "invocation_ids",
        "input_artifact_names",
        "output_artifact_names",
    )
    @classmethod
    def validate_non_empty_string_list(cls, value: list[str]) -> list[str]:
        cleaned = [" ".join(item.split()) for item in value]
        if any(not item for item in cleaned):
            raise ValueError("list entries must not be empty")
        return cleaned


class ArtifactReference(StrictModel):
    name: str
    relative_path: str
    producing_phase: str
    checksum: str | None = None

    @field_validator("name", "relative_path", "producing_phase")
    @classmethod
    def validate_non_empty_string(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("field must not be empty")
        return cleaned


class RunContext(StrictModel):
    run_id: str
    document_id: str
    input_sha256: str
    input_path: Path
    run_dir: Path
    pipeline_version: str
    paper_id: str | None = None

    @field_validator("run_id", "document_id", "input_sha256", "pipeline_version")
    @classmethod
    def validate_non_empty_string(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("field must not be empty")
        return cleaned

    @field_validator("paper_id")
    @classmethod
    def validate_optional_non_empty_string(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("paper_id must not be empty when provided")
        return cleaned


class RunManifest(StrictModel):
    schema_version: str = "2.0"
    run_id: str
    input_file: str
    document_id: str | None = None
    input_sha256: str | None = None
    pipeline_version: str
    paper_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    fingerprint: RunFingerprint | None = None
    phases: dict[str, list[PhaseExecution]]
    artifacts: list[ArtifactReference] = Field(default_factory=list)

    @field_validator("phases", mode="before")
    @classmethod
    def normalize_phase_values(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        normalized: dict[str, object] = {}
        for phase_name, phase_value in value.items():
            if isinstance(phase_value, list):
                normalized[phase_name] = phase_value
            elif isinstance(phase_value, (str, PhaseStatus)):
                normalized[phase_name] = [{"status": phase_value}]
            else:
                normalized[phase_name] = [phase_value]
        return normalized

    @model_validator(mode="after")
    def validate_phase_execution_scopes(self) -> RunManifest:
        running_count = 0
        for phase_name, executions in self.phases.items():
            if is_global_phase(phase_name):
                if len(executions) != 1:
                    raise ValueError(
                        f"global phase {phase_name!r} must have exactly one execution"
                    )
                if executions[0].scope_design_id is not None:
                    raise ValueError(
                        f"global phase {phase_name!r} cannot have a design scope"
                    )
            elif is_per_design_phase(phase_name):
                for execution in executions:
                    if execution.scope_design_id is None:
                        raise ValueError(
                            f"per-design phase {phase_name!r} requires a design scope"
                        )

            scope_ids = [execution.scope_design_id for execution in executions]
            if len(scope_ids) != len(set(scope_ids)):
                raise ValueError(
                    f"duplicate execution scope for phase {phase_name!r}"
                )
            running_count += sum(
                execution.status == PhaseStatus.RUNNING
                for execution in executions
            )
        if running_count > 1:
            raise ValueError("only one phase execution may be running")
        return self

    @field_validator("schema_version", "run_id", "input_file", "pipeline_version")
    @classmethod
    def validate_non_empty_string(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("field must not be empty")
        return cleaned

    @field_validator("paper_id")
    @classmethod
    def validate_optional_non_empty_string(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("paper_id must not be empty when provided")
        return cleaned

    @field_validator("document_id", "input_sha256")
    @classmethod
    def validate_optional_identity(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("identity field must not be empty when provided")
        return cleaned

    def add_artifact(self, artifact: ArtifactReference) -> None:
        self.artifacts.append(artifact)
