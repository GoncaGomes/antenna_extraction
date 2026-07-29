from __future__ import annotations

from pydantic import SecretStr

from antenna_ingest.models import client as client_module
from antenna_ingest.models.client import (
    build_model_client,
    build_openai_compatible_client,
)
from antenna_ingest.settings import AntennaIngestSettings, ModelRole


def test_build_openai_compatible_client_passes_configuration(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        client_module,
        "OpenAI",
        lambda **kwargs: calls.append(kwargs) or object(),
    )

    build_openai_compatible_client(
        base_url="https://example.invalid/openai",
        api_key="secret",
        timeout_seconds=45,
    )

    assert calls == [
        {
            "base_url": "https://example.invalid/openai",
            "api_key": "secret",
            "timeout": 45,
        }
    ]


def test_build_model_client_uses_selected_role_timeout(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        client_module,
        "OpenAI",
        lambda **kwargs: calls.append(kwargs) or object(),
    )

    build_model_client(_settings(), ModelRole.ARCHITECTURE_AUTHOR)

    assert calls[0]["base_url"] == "https://skynet.invalid/openai"
    assert calls[0]["api_key"] == "secret-key"
    assert calls[0]["timeout"] == 720


def _settings() -> AntennaIngestSettings:
    return AntennaIngestSettings(
        skynet_base_url="https://skynet.invalid/openai",
        skynet_api_key=SecretStr("secret-key"),
        document_extractor_model="extractor",
        architecture_author_model="author",
        document_extractor_timeout_seconds=240,
        architecture_author_timeout_seconds=720,
        _env_file=None,
    )
