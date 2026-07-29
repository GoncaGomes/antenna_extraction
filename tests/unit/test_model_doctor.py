from __future__ import annotations

from pydantic import SecretStr

from antenna_ingest.models.doctor import run_endpoint_doctor
from antenna_ingest.settings import AntennaIngestSettings, ModelRole


class FakeMessage:
    content = "ENDPOINT-OK"


class FakeChoice:
    message = FakeMessage()


class FakeResponse:
    choices = [FakeChoice()]


class FakeCompletions:
    def __init__(self, should_raise: bool = False):
        self.should_raise = should_raise
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.should_raise:
            raise RuntimeError("connection failed")
        return FakeResponse()


class FakeClient:
    def __init__(self, should_raise: bool = False):
        self.completions = FakeCompletions(should_raise)
        self.chat = type("FakeChat", (), {"completions": self.completions})()


def test_doctor_checks_only_explicitly_selected_role() -> None:
    client = FakeClient()

    result = run_endpoint_doctor(
        ModelRole.ARCHITECTURE_AUTHOR,
        settings=_settings(),
        client=client,
    )

    assert result.ok is True
    assert result.model_role == ModelRole.ARCHITECTURE_AUTHOR
    assert result.model == "author"
    assert result.response_text == "ENDPOINT-OK"
    assert len(client.completions.calls) == 1
    call = client.completions.calls[0]
    assert call["model"] == "author"
    assert call["temperature"] == 0
    assert "tools" not in call
    assert "response_format" not in call


def test_doctor_returns_failure_for_endpoint_error() -> None:
    result = run_endpoint_doctor(
        ModelRole.DOCUMENT_EXTRACTOR,
        settings=_settings(),
        client=FakeClient(should_raise=True),
    )

    assert result.ok is False
    assert result.model == "extractor"
    assert result.error == "connection failed"


def _settings() -> AntennaIngestSettings:
    return AntennaIngestSettings(
        skynet_base_url="https://skynet.invalid/openai",
        skynet_api_key=SecretStr("secret-key"),
        document_extractor_model="extractor",
        architecture_author_model="author",
        _env_file=None,
    )
