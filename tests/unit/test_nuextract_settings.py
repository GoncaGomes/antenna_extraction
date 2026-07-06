from __future__ import annotations

import pytest
from pydantic import ValidationError

from antenna_ingest.nuextract.settings import NuExtractSettings


def test_settings_load_preferred_names_from_environment(monkeypatch) -> None:
    _set_valid_environment(monkeypatch)
    monkeypatch.setenv("CANONICALIZER_MODEL", "canonicalizer")
    monkeypatch.setenv("VERIFIER_MODEL", "verifier")
    monkeypatch.setenv("NUEXTRACT_TIMEOUT_SECONDS", "240")
    monkeypatch.setenv("CANONICALIZER_TIMEOUT_SECONDS", "720")

    settings = NuExtractSettings()

    assert settings.skynet_base_url == "https://skynet.av.it.pt/openai"
    assert settings.nuextract_model == "nuextract3"
    assert settings.canonicalizer_model == "canonicalizer"
    assert settings.verifier_model == "verifier"
    assert settings.nuextract_timeout_seconds == 240
    assert settings.canonicalizer_timeout_seconds == 720
    assert settings.skynet_api_key.get_secret_value() == "secret-key"


def test_legacy_base_url_and_model_names_are_supported(monkeypatch) -> None:
    monkeypatch.delenv("SKYNET_BASE_URL", raising=False)
    monkeypatch.delenv("NUEXTRACT_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://legacy.invalid/openai")
    monkeypatch.setenv("OLLAMA_MODEL", "legacy-nuextract")
    monkeypatch.setenv("SKYNET_API_KEY", "secret-key")

    settings = NuExtractSettings()

    assert settings.skynet_base_url == "https://legacy.invalid/openai"
    assert settings.nuextract_model == "legacy-nuextract"


def test_role_and_timeout_defaults(monkeypatch) -> None:
    _set_valid_environment(monkeypatch)

    settings = NuExtractSettings()

    assert settings.canonicalizer_model == "gemma-4-31b-it"
    assert settings.verifier_model == "gemma-4-31b-it"
    assert settings.nuextract_timeout_seconds == 180
    assert settings.canonicalizer_timeout_seconds == 600


@pytest.mark.parametrize(
    "environment_name",
    [
        "SKYNET_BASE_URL",
        "NUEXTRACT_MODEL",
        "CANONICALIZER_MODEL",
        "VERIFIER_MODEL",
    ],
)
def test_blank_string_settings_fail_validation(monkeypatch, environment_name) -> None:
    _set_valid_environment(monkeypatch)
    monkeypatch.setenv(environment_name, " ")

    with pytest.raises(ValidationError):
        NuExtractSettings()


@pytest.mark.parametrize(
    "environment_name",
    ["NUEXTRACT_TIMEOUT_SECONDS", "CANONICALIZER_TIMEOUT_SECONDS"],
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
        NuExtractSettings()


def test_blank_skynet_api_key_fails_validation(monkeypatch) -> None:
    _set_valid_environment(monkeypatch)
    monkeypatch.setenv("SKYNET_API_KEY", " ")

    with pytest.raises(ValidationError):
        NuExtractSettings()


def test_secret_value_is_not_exposed_by_model_dump(monkeypatch) -> None:
    _set_valid_environment(monkeypatch)

    dumped = NuExtractSettings().model_dump()

    assert "secret-key" not in str(dumped)


def _set_valid_environment(monkeypatch) -> None:
    monkeypatch.setenv("SKYNET_BASE_URL", "https://skynet.av.it.pt/openai")
    monkeypatch.setenv("NUEXTRACT_MODEL", "nuextract3")
    monkeypatch.setenv("SKYNET_API_KEY", "secret-key")
