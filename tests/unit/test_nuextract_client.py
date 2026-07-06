from __future__ import annotations

from pydantic import SecretStr

from antenna_ingest.nuextract import client as client_module
from antenna_ingest.nuextract.client import (
    build_nuextract_client,
    build_openai_compatible_client,
)
from antenna_ingest.nuextract.settings import NuExtractSettings


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


def test_build_nuextract_client_uses_role_settings(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        client_module,
        "OpenAI",
        lambda **kwargs: calls.append(kwargs) or object(),
    )
    settings = NuExtractSettings(
        SKYNET_BASE_URL="https://skynet.invalid/openai",
        SKYNET_API_KEY=SecretStr("secret-key"),
        NUEXTRACT_MODEL="nuextract3",
        NUEXTRACT_TIMEOUT_SECONDS=240,
    )

    build_nuextract_client(settings)

    assert calls[0]["base_url"] == "https://skynet.invalid/openai"
    assert calls[0]["api_key"] == "secret-key"
    assert calls[0]["timeout"] == 240
