from __future__ import annotations

from types import SimpleNamespace

import pytest

from antenna_ingest.canonicalization.doctor import (
    DOCTOR_RESPONSE_FORMAT,
    CanonicalizationDoctorResult,
    run_canonicalization_doctor,
)
from antenna_ingest.cli import main
from antenna_ingest.nuextract.settings import NuExtractSettings


def test_doctor_accepts_native_tool_call_and_strict_output() -> None:
    client = FakeClient([tool_response(), final_response('{"status":"ok"}')])

    result = run_canonicalization_doctor(
        settings=make_settings(),
        client=client,
        enable_thinking=False,
    )

    assert result.ok is True
    assert result.tool_call_ok is True
    assert result.structured_output_ok is True
    assert result.response_text == '{"status":"ok"}'
    assert len(client.completions.calls) == 2
    assert all(
        call["response_format"] == DOCTOR_RESPONSE_FORMAT
        for call in client.completions.calls
    )
    assert all(
        call["extra_body"]
        == {"chat_template_kwargs": {"enable_thinking": False}}
        for call in client.completions.calls
    )


def test_doctor_rejects_missing_tool_call() -> None:
    client = FakeClient([final_response('{"status":"ok"}')])

    result = run_canonicalization_doctor(
        settings=make_settings(),
        client=client,
    )

    assert result.ok is False
    assert result.tool_call_ok is False
    assert result.structured_output_ok is False
    assert result.error == "backend did not return a native tool call"


def test_doctor_rejects_malformed_final_json() -> None:
    client = FakeClient([tool_response(), final_response("not-json")])

    result = run_canonicalization_doctor(
        settings=make_settings(),
        client=client,
    )

    assert result.ok is False
    assert result.tool_call_ok is True
    assert result.structured_output_ok is False
    assert result.response_text == "not-json"
    assert result.error


@pytest.mark.parametrize(
    ("result", "expected_exit_code"),
    [
        (
            CanonicalizationDoctorResult(
                ok=True,
                model="gemma-test",
                tool_call_ok=True,
                structured_output_ok=True,
                response_text='{"status":"ok"}',
            ),
            0,
        ),
        (
            CanonicalizationDoctorResult(
                ok=False,
                model="gemma-test",
                tool_call_ok=False,
                structured_output_ok=False,
                error="probe failed",
            ),
            1,
        ),
    ],
)
def test_doctor_cli_exit_status_matches_result(
    monkeypatch,
    capsys,
    result: CanonicalizationDoctorResult,
    expected_exit_code: int,
) -> None:
    monkeypatch.setattr(
        "antenna_ingest.cli.run_canonicalization_doctor",
        lambda: result,
    )

    exit_code = main(["canonicalization", "doctor"])

    assert exit_code == expected_exit_code
    output = capsys.readouterr().out
    assert "Model: gemma-test" in output
    assert "Tool calling:" in output
    assert "Structured output:" in output


class FakeClient:
    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self.completions = FakeCompletions(responses)
        self.chat = SimpleNamespace(completions=self.completions)


class FakeCompletions:
    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self.responses = iter(responses)
        self.calls: list[dict] = []

    def create(self, **kwargs) -> SimpleNamespace:
        self.calls.append(kwargs)
        return next(self.responses)


def tool_response() -> SimpleNamespace:
    tool_call = SimpleNamespace(
        id="doctor_call_1",
        type="function",
        function=SimpleNamespace(
            name="get_test_value",
            arguments='{"query":"canonicalization doctor"}',
        ),
    )
    message = SimpleNamespace(content=None, tool_calls=[tool_call])
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def final_response(content: str) -> SimpleNamespace:
    message = SimpleNamespace(content=content, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def make_settings() -> NuExtractSettings:
    return NuExtractSettings(
        _env_file=None,
        SKYNET_BASE_URL="https://example.invalid/v1",
        SKYNET_API_KEY="test-key",
        NUEXTRACT_MODEL="test-nuextract",
        CANONICALIZER_MODEL="gemma-test",
        CANONICALIZER_TIMEOUT_SECONDS=30,
    )
