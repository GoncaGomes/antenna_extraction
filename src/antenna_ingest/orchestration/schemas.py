from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    failure_reference: str | None = None


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
    schema_version: str = "1.1"
    run_id: str
    input_file: str
    document_id: str | None = None
    input_sha256: str | None = None
    pipeline_version: str
    paper_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    fingerprint: RunFingerprint | None = None
    phases: dict[str, PhaseExecution]
    artifacts: list[ArtifactReference] = Field(default_factory=list)

    @field_validator("phases", mode="before")
    @classmethod
    def normalize_phase_values(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        return {
            phase_name: (
                {"status": phase_value}
                if isinstance(phase_value, (str, PhaseStatus))
                else phase_value
            )
            for phase_name, phase_value in value.items()
        }

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
