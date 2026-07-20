from __future__ import annotations

import json

from pydantic import ValidationError

from antenna_ingest.orchestration.failures import (
    is_retryable_failure,
    sanitize_failure_message,
)
from antenna_ingest.orchestration.schemas import PhaseExecution


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
