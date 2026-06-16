from __future__ import annotations

import pytest
from pydantic import ValidationError

from antenna_ingest.nuextract.settings import NuExtractSettings


def test_settings_load_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://skynet.av.it.pt/openai")
    monkeypatch.setenv("OLLAMA_MODEL", "nuextract3")
    monkeypatch.setenv("SKYNET_API_KEY", "secret-key")

    settings = NuExtractSettings()

    assert settings.openai_base_url == "https://skynet.av.it.pt/openai"
    assert settings.ollama_model == "nuextract3"
    assert settings.skynet_api_key.get_secret_value() == "secret-key"


def test_blank_openai_base_url_fails_validation(monkeypatch) -> None:
    _set_valid_environment(monkeypatch)
    monkeypatch.setenv("OPENAI_BASE_URL", " ")

    with pytest.raises(ValidationError):
        NuExtractSettings()


def test_blank_ollama_model_fails_validation(monkeypatch) -> None:
    _set_valid_environment(monkeypatch)
    monkeypatch.setenv("OLLAMA_MODEL", " ")

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
    monkeypatch.setenv("OPENAI_BASE_URL", "https://skynet.av.it.pt/openai")
    monkeypatch.setenv("OLLAMA_MODEL", "nuextract3")
    monkeypatch.setenv("SKYNET_API_KEY", "secret-key")
