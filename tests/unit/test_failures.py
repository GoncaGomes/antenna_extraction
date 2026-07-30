from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from antenna_ingest.orchestration.failures import (
    is_retryable_failure,
    sanitize_failure_message,
    write_failure_record,
)
from antenna_ingest.orchestration.schemas import PhaseExecution
from antenna_ingest.utils.json_io import read_json


def test_retryable_failure_classification_is_conservative() -> None:
    assert is_retryable_failure(TimeoutError("temporary")) is True
    assert is_retryable_failure(ConnectionError("temporary")) is True
    assert is_retryable_failure(FileNotFoundError("missing")) is False
    assert is_retryable_failure(
        json.JSONDecodeError("bad", "{", 0)
    ) is False
    try:
        PhaseExecution.model_validate({"status": "invalid"})
    except ValidationError as error:
        assert is_retryable_failure(error) is False


def test_failure_message_redacts_common_secret_forms() -> None:
    message = (
        "Bearer token-value api_key=secret-value "
        "https://user:password@example.invalid/path"
    )

    sanitized = sanitize_failure_message(message)

    assert "token-value" not in sanitized
    assert "secret-value" not in sanitized
    assert "user:password" not in sanitized


def test_write_failure_record_persists_redacted_error(tmp_path: Path) -> None:
    secrets = (
        "api-secret-value",
        "bearer-secret-value",
        "endpoint-user:endpoint-password",
    )
    error = RuntimeError(
        f"api_key={secrets[0]} "
        f"Bearer {secrets[1]} "
        f"https://{secrets[2]}@example.invalid/v1"
    )

    relative_path = write_failure_record(
        tmp_path,
        phase="page_rendering",
        attempt=2,
        substage="request",
        error=error,
    )

    assert relative_path == (
        "reports/failures/page_rendering_attempt_002.json"
    )
    failure_path = tmp_path / relative_path
    assert failure_path.is_file()
    record = read_json(failure_path)
    persisted_text = failure_path.read_text(encoding="utf-8")
    assert record["phase"] == "page_rendering"
    assert record["exception_type"] == "RuntimeError"
    assert record["message"].count("[redacted]") == 3
    assert all(secret not in persisted_text for secret in secrets)
