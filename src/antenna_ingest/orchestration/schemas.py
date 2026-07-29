from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MANIFEST_SCHEMA_VERSION = "3.0"
RUN_PHASES = (
    "run_initialization",
    "page_rendering",
    "paper_extraction",
    "results_publication",
    "architecture_generation",
    "output_validation",
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PhaseStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
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
    attempt: int = Field(default=0, ge=0)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    model_role: str | None = None
    input_artifact_names: list[str] = Field(default_factory=list)
    output_artifact_names: list[str] = Field(default_factory=list)
    failure_reference: str | None = None
    prompt_hash: str | None = None
    schema_hash: str | None = None

    @field_validator(
        "model_role",
        "failure_reference",
        "prompt_hash",
        "schema_hash",
    )
    @classmethod
    def validate_optional_non_empty_string(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("field must not be empty when provided")
        return cleaned

    @field_validator("input_artifact_names", "output_artifact_names")
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
    schema_version: Literal["3.0"] = MANIFEST_SCHEMA_VERSION
    run_id: str
    input_file: str
    document_id: str
    input_sha256: str
    pipeline_version: str
    paper_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    fingerprint: RunFingerprint
    phases: dict[str, PhaseExecution]
    artifacts: list[ArtifactReference] = Field(default_factory=list)

    @field_validator(
        "schema_version",
        "run_id",
        "input_file",
        "document_id",
        "input_sha256",
        "pipeline_version",
    )
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

    @model_validator(mode="after")
    def validate_phase_set_and_running_count(self) -> RunManifest:
        if tuple(self.phases) != RUN_PHASES:
            raise ValueError(
                "manifest phases must match the ordered pipeline phase set"
            )
        running_count = sum(
            execution.status == PhaseStatus.RUNNING
            for execution in self.phases.values()
        )
        if running_count > 1:
            raise ValueError("only one phase may be running")
        return self

    def add_artifact(self, artifact: ArtifactReference) -> None:
        self.artifacts.append(artifact)
