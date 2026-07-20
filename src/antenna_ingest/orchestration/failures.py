from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import Field, ValidationError

from antenna_ingest.orchestration.schemas import StrictModel
from antenna_ingest.utils.json_io import write_json


class FailureRecord(StrictModel):
    failure_id: str
    phase: str
    substage: str
    occurred_at: datetime
    exception_type: str
    message: str
    retryable: bool
    invocation_id: str | None = None
    response_artifact: str | None = None
    partial_artifacts: list[str] = Field(default_factory=list)


def write_failure_record(
    run_dir: Path,
    *,
    phase: str,
    attempt: int,
    substage: str,
    error: Exception,
    invocation_id: str | None = None,
    response_artifact: str | None = None,
    partial_artifacts: list[str] | None = None,
) -> str:
    relative_path = Path("reports") / "failures" / (
        f"{phase}_attempt_{attempt:03d}.json"
    )
    record = FailureRecord(
        failure_id=f"failure_{uuid4().hex[:12]}",
        phase=phase,
        substage=substage,
        occurred_at=datetime.now(timezone.utc),
        exception_type=type(error).__name__,
        message=sanitize_failure_message(str(error)),
        retryable=is_retryable_failure(error),
        invocation_id=invocation_id,
        response_artifact=response_artifact,
        partial_artifacts=partial_artifacts or [],
    )
    write_json(
        Path(run_dir) / relative_path,
        record.model_dump(mode="json"),
    )
    return relative_path.as_posix()


def is_retryable_failure(error: Exception) -> bool:
    if isinstance(error, (TimeoutError, ConnectionError)):
        return True
    if isinstance(error, (FileNotFoundError, json.JSONDecodeError, ValidationError)):
        return False
    status_code = getattr(error, "status_code", None)
    if isinstance(status_code, int):
        return status_code in {408, 429} or status_code >= 500
    error_name = type(error).__name__.lower()
    return "timeout" in error_name or "connection" in error_name


def sanitize_failure_message(message: str) -> str:
    sanitized = re.sub(r"(?i)bearer\s+[^\s,;]+", "Bearer [redacted]", message)
    sanitized = re.sub(
        r"(?i)(api[_-]?key|authorization|token)(\s*[=:]\s*)[^\s,;&]+",
        r"\1\2[redacted]",
        sanitized,
    )
    return re.sub(r"(https?://)[^/@\s]+@", r"\1[redacted]@", sanitized)
