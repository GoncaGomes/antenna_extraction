from __future__ import annotations

from typing import Literal

from antenna_ingest.nuextract.client import build_openai_compatible_client
from antenna_ingest.nuextract.settings import (
    NuExtractSettings,
    load_nuextract_settings,
)
from antenna_ingest.orchestration.schemas import StrictModel


class CanonicalizationDoctorOutput(StrictModel):
    status: Literal["ok"]


class CanonicalizationDoctorResult(StrictModel):
    ok: bool
    model: str
    tool_call_ok: bool
    structured_output_ok: bool
    response_text: str | None = None
    error: str | None = None


DOCTOR_TOOL = {
    "type": "function",
    "function": {
        "name": "get_test_value",
        "description": "Return a diagnostic test value.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}

DOCTOR_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "canonicalization_doctor_output",
        "strict": True,
        "schema": CanonicalizationDoctorOutput.model_json_schema(),
    },
}


def run_canonicalization_doctor(
    settings: NuExtractSettings | None = None,
    client: object | None = None,
    enable_thinking: bool = True,
) -> CanonicalizationDoctorResult:
    settings = settings or load_nuextract_settings()
    if client is None:
        client = build_openai_compatible_client(
            base_url=settings.skynet_base_url,
            api_key=settings.skynet_api_key.get_secret_value(),
            timeout_seconds=settings.canonicalizer_timeout_seconds,
        )

    tool_call_ok = False
    response_text: str | None = None
    messages = [
        {
            "role": "user",
            "content": (
                "Call get_test_value with query canonicalization doctor. "
                "Do not answer directly."
            ),
        }
    ]
    request_options = {
        "model": settings.canonicalizer_model,
        "tools": [DOCTOR_TOOL],
        "temperature": 0.0,
        "response_format": DOCTOR_RESPONSE_FORMAT,
        "extra_body": {
            "chat_template_kwargs": {"enable_thinking": enable_thinking}
        },
    }

    try:
        response = client.chat.completions.create(
            messages=messages,
            tool_choice={
                "type": "function",
                "function": {"name": "get_test_value"},
            },
            **request_options,
        )
        message = response.choices[0].message
        tool_calls = message.tool_calls or []
        if not tool_calls:
            raise RuntimeError("backend did not return a native tool call")
        tool_call = tool_calls[0]
        if tool_call.function.name != "get_test_value":
            raise RuntimeError(
                f"backend returned unexpected tool: {tool_call.function.name}"
            )
        tool_call_ok = True

        messages.append(
            {
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments,
                        },
                    }
                ],
            }
        )
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": '{"value":"test"}',
            }
        )
        messages.append(
            {
                "role": "user",
                "content": 'Return exactly the structured object {"status":"ok"}.',
            }
        )

        response = client.chat.completions.create(
            messages=messages,
            tool_choice="none",
            **request_options,
        )
        response_text = response.choices[0].message.content
        if not isinstance(response_text, str):
            raise RuntimeError("backend returned no structured response text")
        CanonicalizationDoctorOutput.model_validate_json(response_text)
        return CanonicalizationDoctorResult(
            ok=True,
            model=settings.canonicalizer_model,
            tool_call_ok=True,
            structured_output_ok=True,
            response_text=response_text,
        )
    except Exception as error:
        return CanonicalizationDoctorResult(
            ok=False,
            model=settings.canonicalizer_model,
            tool_call_ok=tool_call_ok,
            structured_output_ok=False,
            response_text=response_text,
            error=str(error),
        )
