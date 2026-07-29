from __future__ import annotations

import pytest
from pydantic import ValidationError

from antenna_ingest.settings import AntennaIngestSettings, ModelRole


def test_settings_load_role_names_from_environment(monkeypatch) -> None:
    _set_valid_environment(monkeypatch)
    monkeypatch.setenv("DOCUMENT_EXTRACTOR_TIMEOUT_SECONDS", "240")
    monkeypatch.setenv("ARCHITECTURE_AUTHOR_TIMEOUT_SECONDS", "720")

    settings = AntennaIngestSettings(_env_file=None)

    assert settings.skynet_base_url == "https://skynet.invalid/openai"
    assert settings.model_for_role(ModelRole.DOCUMENT_EXTRACTOR) == "extractor"
    assert settings.model_for_role(ModelRole.ARCHITECTURE_AUTHOR) == "author"
    assert settings.timeout_for_role(ModelRole.DOCUMENT_EXTRACTOR) == 240
    assert settings.timeout_for_role(ModelRole.ARCHITECTURE_AUTHOR) == 720
    assert settings.skynet_api_key.get_secret_value() == "secret-key"


@pytest.mark.parametrize(
    "environment_name",
    [
        "SKYNET_BASE_URL",
        "DOCUMENT_EXTRACTOR_MODEL",
        "ARCHITECTURE_AUTHOR_MODEL",
    ],
)
def test_blank_required_strings_fail_validation(monkeypatch, environment_name) -> None:
    _set_valid_environment(monkeypatch)
    monkeypatch.setenv(environment_name, " ")

    with pytest.raises(ValidationError):
        AntennaIngestSettings(_env_file=None)


@pytest.mark.parametrize(
    "environment_name",
    [
        "DOCUMENT_EXTRACTOR_TIMEOUT_SECONDS",
        "ARCHITECTURE_AUTHOR_TIMEOUT_SECONDS",
    ],
)
@pytest.mark.parametrize("value", ["0", "-1"])
def test_non_positive_timeouts_fail_validation(
    monkeypatch,
    environment_name,
    value,
) -> None:
    _set_valid_environment(monkeypatch)
    monkeypatch.setenv(environment_name, value)

    with pytest.raises(ValidationError):
        AntennaIngestSettings(_env_file=None)


def test_blank_api_key_fails_validation(monkeypatch) -> None:
    _set_valid_environment(monkeypatch)
    monkeypatch.setenv("SKYNET_API_KEY", " ")

    with pytest.raises(ValidationError):
        AntennaIngestSettings(_env_file=None)


def test_api_key_is_excluded_from_dumps(monkeypatch) -> None:
    _set_valid_environment(monkeypatch)

    dumped = AntennaIngestSettings(_env_file=None).model_dump(mode="json")

    assert "skynet_api_key" not in dumped
    assert "secret-key" not in str(dumped)


def _set_valid_environment(monkeypatch) -> None:
    monkeypatch.setenv("SKYNET_BASE_URL", "https://skynet.invalid/openai")
    monkeypatch.setenv("SKYNET_API_KEY", "secret-key")
    monkeypatch.setenv("DOCUMENT_EXTRACTOR_MODEL", "extractor")
    monkeypatch.setenv("ARCHITECTURE_AUTHOR_MODEL", "author")
