from __future__ import annotations

from types import SimpleNamespace

import pytest

from antenna_ingest.canonicalization.doctor import (
    DOCTOR_RESPONSE_FORMAT,
    DOCTOR_TOOL,
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

    first_call, second_call = client.completions.calls
    assert first_call["tools"] == [DOCTOR_TOOL]
    assert first_call["tool_choice"] == {
        "type": "function",
        "function": {"name": "get_test_value"},
    }
    assert "response_format" not in first_call
    assert second_call["response_format"] == DOCTOR_RESPONSE_FORMAT
    assert "tools" not in second_call
    assert "tool_choice" not in second_call
    assert all(
        call["extra_body"]
        == {"chat_template_kwargs": {"enable_thinking": False}}
        for call in client.completions.calls
    )

    second_messages = second_call["messages"]
    assert second_messages[1] == {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "doctor_call_1",
                "type": "function",
                "function": {
                    "name": "get_test_value",
                    "arguments": '{"query":"canonicalization doctor"}',
                },
            }
        ],
    }
    assert second_messages[2] == {
        "role": "tool",
        "tool_call_id": "doctor_call_1",
        "content": '{"value":"test"}',
    }


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


def test_doctor_rejects_unexpected_tool_name() -> None:
    client = FakeClient([tool_response(name="other_tool")])

    result = run_canonicalization_doctor(
        settings=make_settings(),
        client=client,
    )

    assert result.ok is False
    assert result.tool_call_ok is False
    assert result.structured_output_ok is False
    assert result.error == "backend returned unexpected tool: other_tool"


def test_doctor_rejects_malformed_tool_arguments() -> None:
    client = FakeClient([tool_response(arguments="{invalid json")])

    result = run_canonicalization_doctor(
        settings=make_settings(),
        client=client,
    )

    assert result.ok is False
    assert result.tool_call_ok is False
    assert result.structured_output_ok is False
    assert result.error == "backend returned invalid tool arguments"


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


def test_doctor_rejects_schema_invalid_final_json() -> None:
    client = FakeClient([tool_response(), final_response('{"status":"bad"}')])

    result = run_canonicalization_doctor(
        settings=make_settings(),
        client=client,
    )

    assert result.ok is False
    assert result.tool_call_ok is True
    assert result.structured_output_ok is False
    assert result.response_text == '{"status":"bad"}'
    assert result.error


@pytest.mark.parametrize("enable_thinking", [True, False])
def test_doctor_forwards_thinking_to_both_requests(
    enable_thinking: bool,
) -> None:
    client = FakeClient([tool_response(), final_response('{"status":"ok"}')])

    result = run_canonicalization_doctor(
        settings=make_settings(),
        client=client,
        enable_thinking=enable_thinking,
    )

    assert result.ok is True
    assert all(
        call["extra_body"]
        == {"chat_template_kwargs": {"enable_thinking": enable_thinking}}
        for call in client.completions.calls
    )


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
    expected_status = "PASSED" if result.ok else "FAILED"
    assert f"Tool calling: {expected_status}" in output
    assert f"Structured output: {expected_status}" in output
    assert f"Status: {expected_status}" in output


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


def tool_response(
    name: str = "get_test_value",
    arguments: str = '{"query":"canonicalization doctor"}',
) -> SimpleNamespace:
    tool_call = SimpleNamespace(
        id="doctor_call_1",
        type="function",
        function=SimpleNamespace(
            name=name,
            arguments=arguments,
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
