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
    input_path: Path
    run_dir: Path
    pipeline_version: str
    paper_id: str | None = None

    @field_validator("run_id", "pipeline_version")
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
    run_id: str
    input_file: str
    pipeline_version: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    phase_status: dict[str, PhaseStatus]
    artifacts: list[ArtifactReference] = Field(default_factory=list)

    @field_validator("run_id", "input_file", "pipeline_version")
    @classmethod
    def validate_non_empty_string(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("field must not be empty")
        return cleaned

    def add_artifact(self, artifact: ArtifactReference) -> None:
        self.artifacts.append(artifact)
