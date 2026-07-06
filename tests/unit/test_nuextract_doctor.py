from __future__ import annotations

from pydantic import SecretStr

from antenna_ingest.nuextract.doctor import run_nuextract_doctor
from antenna_ingest.nuextract.settings import NuExtractSettings


class FakeMessage:
    content = "NUEXTRACT3-OK"


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


class FakeChat:
    def __init__(self, completions: FakeCompletions):
        self.completions = completions


class FakeClient:
    def __init__(self, should_raise: bool = False):
        self.completions = FakeCompletions(should_raise=should_raise)
        self.chat = FakeChat(self.completions)


def test_doctor_success_returns_ok() -> None:
    client = FakeClient()

    result = run_nuextract_doctor(settings=_settings(), client=client)

    assert result.ok is True
    assert result.base_url == "https://skynet.av.it.pt/openai"
    assert result.model == "nuextract3"
    assert result.response_text == "NUEXTRACT3-OK"


def test_doctor_passes_configured_model_and_prompt() -> None:
    client = FakeClient()

    run_nuextract_doctor(settings=_settings(), client=client)

    call = client.completions.calls[0]
    assert call["model"] == "nuextract3"
    assert "NUEXTRACT3-OK" in call["messages"][0]["content"]
    assert call["temperature"] == 0


def test_doctor_exception_returns_failed_result() -> None:
    result = run_nuextract_doctor(
        settings=_settings(),
        client=FakeClient(should_raise=True),
    )

    assert result.ok is False
    assert result.base_url == "https://skynet.av.it.pt/openai"
    assert result.model == "nuextract3"
    assert result.error == "connection failed"


def _settings() -> NuExtractSettings:
    return NuExtractSettings(
        SKYNET_BASE_URL="https://skynet.av.it.pt/openai",
        NUEXTRACT_MODEL="nuextract3",
        SKYNET_API_KEY=SecretStr("secret-key"),
    )
