from __future__ import annotations

import json
from typing import Any, TypedDict

from antenna_ingest.canonicalization.agent import (
    CANONICAL_DESIGN_RESPONSE_FORMAT,
    SEARCH_EVIDENCE_TOOL,
)
from antenna_ingest.canonicalization.schemas import CanonicalDesignRecord
from antenna_ingest.nuextract.client import build_openai_compatible_client
from antenna_ingest.nuextract.settings import (
    NuExtractSettings,
    load_nuextract_settings,
)


class ProbeResult(TypedDict):
    probe: str
    enable_thinking: bool
    passed: bool
    tool_call_returned: bool | None
    structured_output_valid: bool | None
    content_preview: str | None
    error: str | None


TOOL_MESSAGES = [
    {
        "role": "system",
        "content": (
            "You are testing native function calling. "
            "You must call the provided search_evidence function. "
            "Do not answer with normal text."
        ),
    },
    {
        "role": "user",
        "content": (
            'Call search_evidence exactly once with query '
            '"FR4 substrate thickness", top_k 3, and context_window 0.'
        ),
    },
]

STRUCTURED_MESSAGES = [
    {
        "role": "system",
        "content": (
            "Return only a valid canonical design record matching the "
            "provided JSON Schema. Do not use Markdown fences or add prose."
        ),
    },
    {
        "role": "user",
        "content": (
            "Return a minimal canonical design record for a synthetic paper. "
            "Use schema_name canonical_design_record_v1. "
            "The final design was selected from evidence ev_probe. "
            "Set reconstruction_status to unknown. "
            "Do not invent additional objects or results."
        ),
    },
]

COMBINED_MESSAGES = [
    {
        "role": "system",
        "content": (
            "You must first call search_evidence. "
            "Do not produce the final canonical record before receiving "
            "the tool result."
        ),
    },
    {
        "role": "user",
        "content": (
            'Call search_evidence with query "final antenna design", '
            "top_k 3, and context_window 0."
        ),
    },
]

FINAL_CONTINUATION = {
    "role": "user",
    "content": (
        "Using the returned evidence, now produce the minimal final canonical "
        "design record. Cite ev_probe in the design evidence_ids. "
        "Do not call another tool."
    ),
}

SYNTHETIC_TOOL_RESULT = {
    "query": "final antenna design",
    "result_count": 1,
    "results": [
        {
            "evidence_id": "ev_probe",
            "source_type": "block",
            "page": 1,
            "kind": "paragraph",
            "section": "Antenna Design",
            "caption": None,
            "text": "The final proposed antenna is the selected design.",
            "score": 10.0,
            "match_reasons": ["probe"],
        }
    ],
}

FORCED_TOOL_CHOICE = {
    "type": "function",
    "function": {"name": "search_evidence"},
}


def _new_result(probe: str, enable_thinking: bool) -> ProbeResult:
    return {
        "probe": probe,
        "enable_thinking": enable_thinking,
        "passed": False,
        "tool_call_returned": None,
        "structured_output_valid": None,
        "content_preview": None,
        "error": None,
    }


def _extra_body(enable_thinking: bool) -> dict[str, Any]:
    return {
        "chat_template_kwargs": {
            "enable_thinking": enable_thinking,
        }
    }


def _start_probe(name: str, enable_thinking: bool) -> None:
    thinking = "on" if enable_thinking else "off"
    print(f"\n=== {name} | thinking={thinking} ===", flush=True)


def _inspect_message(
    response: Any,
    result: ProbeResult,
    *,
    stage: str,
) -> tuple[Any, list[Any], str | None]:
    message = response.choices[0].message
    tool_calls = message.tool_calls or []
    content = message.content if isinstance(message.content, str) else None
    preview = content[:500] if content else None
    result["content_preview"] = preview

    print(f"{stage} tool call returned: {bool(tool_calls)}", flush=True)
    print(f"{stage} tool call count: {len(tool_calls)}", flush=True)
    for tool_call in tool_calls:
        print(f"{stage} tool name: {tool_call.function.name}", flush=True)
        print(
            f"{stage} tool arguments: {tool_call.function.arguments}",
            flush=True,
        )
    print(f"{stage} content exists: {bool(content)}", flush=True)
    if preview is not None:
        print(f"{stage} content preview: {preview}", flush=True)
    return message, tool_calls, content


def _require_valid_tool_calls(tool_calls: list[Any]) -> None:
    if not tool_calls:
        raise RuntimeError("no native tool call was returned")
    for tool_call in tool_calls:
        if tool_call.function.name != "search_evidence":
            raise ValueError(
                f"unexpected tool name: {tool_call.function.name}"
            )
        try:
            arguments = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError as error:
            raise ValueError("tool arguments are not valid JSON") from error
        if not isinstance(arguments, dict):
            raise ValueError("tool arguments are not a JSON object")


def _append_tool_exchange(
    messages: list[dict[str, Any]],
    message: Any,
    tool_calls: list[Any],
) -> None:
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
                for tool_call in tool_calls
            ],
        }
    )
    synthetic_content = json.dumps(SYNTHETIC_TOOL_RESULT)
    for tool_call in tool_calls:
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": synthetic_content,
            }
        )


def _validate_structured_content(content: str | None) -> None:
    if not content:
        raise RuntimeError("no structured response content was returned")
    CanonicalDesignRecord.model_validate_json(content)


def _record_error(result: ProbeResult, error: Exception) -> ProbeResult:
    result["error"] = f"{type(error).__name__}: {error}"
    print(f"Probe error: {result['error']}", flush=True)
    return result


def probe_tool_only(
    client: Any,
    settings: NuExtractSettings,
    enable_thinking: bool,
    *,
    forced: bool,
) -> ProbeResult:
    name = "Tool only, forced" if forced else "Tool only, auto"
    result = _new_result(name, enable_thinking)
    _start_probe(name, enable_thinking)
    try:
        response = client.chat.completions.create(
            model=settings.canonicalizer_model,
            messages=TOOL_MESSAGES,
            tools=[SEARCH_EVIDENCE_TOOL],
            tool_choice=FORCED_TOOL_CHOICE if forced else "auto",
            temperature=0.0,
            extra_body=_extra_body(enable_thinking),
        )
        _, tool_calls, _ = _inspect_message(
            response,
            result,
            stage="Response",
        )
        result["tool_call_returned"] = bool(tool_calls)
        _require_valid_tool_calls(tool_calls)
        result["passed"] = True
        return result
    except Exception as error:
        return _record_error(result, error)


def probe_structured_only(
    client: Any,
    settings: NuExtractSettings,
    enable_thinking: bool,
) -> ProbeResult:
    name = "Structured output only"
    result = _new_result(name, enable_thinking)
    result["tool_call_returned"] = None
    result["structured_output_valid"] = False
    _start_probe(name, enable_thinking)
    try:
        response = client.chat.completions.create(
            model=settings.canonicalizer_model,
            messages=STRUCTURED_MESSAGES,
            temperature=0.0,
            response_format=CANONICAL_DESIGN_RESPONSE_FORMAT,
            extra_body=_extra_body(enable_thinking),
        )
        _, _, content = _inspect_message(
            response,
            result,
            stage="Response",
        )
        _validate_structured_content(content)
        result["structured_output_valid"] = True
        result["passed"] = True
        print("Direct Pydantic parsing succeeded: True", flush=True)
        return result
    except Exception as error:
        print("Direct Pydantic parsing succeeded: False", flush=True)
        return _record_error(result, error)


def probe_combined_auto(
    client: Any,
    settings: NuExtractSettings,
    enable_thinking: bool,
) -> ProbeResult:
    name = "Combined, auto"
    result = _new_result(name, enable_thinking)
    _start_probe(name, enable_thinking)
    try:
        messages = [dict(message) for message in COMBINED_MESSAGES]
        response = client.chat.completions.create(
            model=settings.canonicalizer_model,
            messages=messages,
            tools=[SEARCH_EVIDENCE_TOOL],
            tool_choice="auto",
            temperature=0.0,
            response_format=CANONICAL_DESIGN_RESPONSE_FORMAT,
            extra_body=_extra_body(enable_thinking),
        )
        message, tool_calls, _ = _inspect_message(
            response,
            result,
            stage="First response",
        )
        result["tool_call_returned"] = bool(tool_calls)
        _require_valid_tool_calls(tool_calls)

        result["structured_output_valid"] = False
        _append_tool_exchange(messages, message, tool_calls)
        messages.append(FINAL_CONTINUATION)
        continuation = client.chat.completions.create(
            model=settings.canonicalizer_model,
            messages=messages,
            tools=[SEARCH_EVIDENCE_TOOL],
            tool_choice="auto",
            temperature=0.0,
            response_format=CANONICAL_DESIGN_RESPONSE_FORMAT,
            extra_body=_extra_body(enable_thinking),
        )
        _, continuation_calls, content = _inspect_message(
            continuation,
            result,
            stage="Continuation",
        )
        if continuation_calls:
            raise RuntimeError("continuation returned another native tool call")
        _validate_structured_content(content)
        result["structured_output_valid"] = True
        result["passed"] = True
        print("Direct Pydantic parsing succeeded: True", flush=True)
        return result
    except Exception as error:
        parse_status = (
            "Not attempted"
            if result["structured_output_valid"] is None
            else "False"
        )
        print(f"Direct Pydantic parsing succeeded: {parse_status}", flush=True)
        return _record_error(result, error)


def probe_combined_forced_first(
    client: Any,
    settings: NuExtractSettings,
    enable_thinking: bool,
) -> ProbeResult:
    name = "Combined first request forced"
    result = _new_result(name, enable_thinking)
    _start_probe(name, enable_thinking)
    try:
        messages = [dict(message) for message in COMBINED_MESSAGES]
        response = client.chat.completions.create(
            model=settings.canonicalizer_model,
            messages=messages,
            tools=[SEARCH_EVIDENCE_TOOL],
            tool_choice=FORCED_TOOL_CHOICE,
            temperature=0.0,
            response_format=CANONICAL_DESIGN_RESPONSE_FORMAT,
            extra_body=_extra_body(enable_thinking),
        )
        message, tool_calls, _ = _inspect_message(
            response,
            result,
            stage="First response",
        )
        result["tool_call_returned"] = bool(tool_calls)
        _require_valid_tool_calls(tool_calls)

        result["structured_output_valid"] = False
        _append_tool_exchange(messages, message, tool_calls)
        messages.append(FINAL_CONTINUATION)
        continuation = client.chat.completions.create(
            model=settings.canonicalizer_model,
            messages=messages,
            temperature=0.0,
            response_format=CANONICAL_DESIGN_RESPONSE_FORMAT,
            extra_body=_extra_body(enable_thinking),
        )
        _, _, content = _inspect_message(
            continuation,
            result,
            stage="Continuation",
        )
        _validate_structured_content(content)
        result["structured_output_valid"] = True
        result["passed"] = True
        print("Direct Pydantic parsing succeeded: True", flush=True)
        return result
    except Exception as error:
        parse_status = (
            "Not attempted"
            if result["structured_output_valid"] is None
            else "False"
        )
        print(f"Direct Pydantic parsing succeeded: {parse_status}", flush=True)
        return _record_error(result, error)


def probe_separated_workflow(
    client: Any,
    settings: NuExtractSettings,
    enable_thinking: bool,
) -> ProbeResult:
    name = "Separated two-stage workflow"
    result = _new_result(name, enable_thinking)
    _start_probe(name, enable_thinking)
    try:
        messages = [dict(message) for message in COMBINED_MESSAGES]
        response = client.chat.completions.create(
            model=settings.canonicalizer_model,
            messages=messages,
            tools=[SEARCH_EVIDENCE_TOOL],
            tool_choice=FORCED_TOOL_CHOICE,
            temperature=0.0,
            extra_body=_extra_body(enable_thinking),
        )
        message, tool_calls, _ = _inspect_message(
            response,
            result,
            stage="Tool response",
        )
        result["tool_call_returned"] = bool(tool_calls)
        _require_valid_tool_calls(tool_calls)

        result["structured_output_valid"] = False
        _append_tool_exchange(messages, message, tool_calls)
        messages.append(FINAL_CONTINUATION)
        structured_response = client.chat.completions.create(
            model=settings.canonicalizer_model,
            messages=messages,
            temperature=0.0,
            response_format=CANONICAL_DESIGN_RESPONSE_FORMAT,
            extra_body=_extra_body(enable_thinking),
        )
        _, _, content = _inspect_message(
            structured_response,
            result,
            stage="Structured response",
        )
        _validate_structured_content(content)
        result["structured_output_valid"] = True
        result["passed"] = True
        print("Direct Pydantic parsing succeeded: True", flush=True)
        return result
    except Exception as error:
        print("Direct Pydantic parsing succeeded: False", flush=True)
        return _record_error(result, error)


def _print_summary(results: list[ProbeResult]) -> None:
    print("\nCapability summary", flush=True)
    print(f"{'Probe':<42} {'Thinking':<10} Result", flush=True)
    print(f"{'-' * 42} {'-' * 10} {'-' * 6}", flush=True)
    for result in results:
        thinking = "on" if result["enable_thinking"] else "off"
        status = "PASS" if result["passed"] else "FAIL"
        print(f"{result['probe']:<42} {thinking:<10} {status}", flush=True)

    failures = [result for result in results if not result["passed"]]
    if not failures:
        return
    print("\nFailure details", flush=True)
    for result in failures:
        thinking = "on" if result["enable_thinking"] else "off"
        print(
            f"- {result['probe']} ({thinking}): "
            f"tool_call_returned={result['tool_call_returned']}, "
            f"structured_output_valid={result['structured_output_valid']}, "
            f"content_preview={result['content_preview']!r}, "
            f"error={result['error']}",
            flush=True,
        )


def main() -> int:
    settings = load_nuextract_settings()
    client = build_openai_compatible_client(
        base_url=settings.skynet_base_url,
        api_key=settings.skynet_api_key.get_secret_value(),
        timeout_seconds=settings.canonicalizer_timeout_seconds,
    )
    print(f"Base URL: {settings.skynet_base_url}", flush=True)
    print(f"Canonicalizer model: {settings.canonicalizer_model}", flush=True)

    results: list[ProbeResult] = []
    for enable_thinking in (True, False):
        results.append(
            probe_tool_only(
                client,
                settings,
                enable_thinking,
                forced=True,
            )
        )
    for enable_thinking in (True, False):
        results.append(
            probe_tool_only(
                client,
                settings,
                enable_thinking,
                forced=False,
            )
        )
    for enable_thinking in (True, False):
        results.append(
            probe_structured_only(client, settings, enable_thinking)
        )
    for enable_thinking in (True, False):
        results.append(
            probe_combined_auto(client, settings, enable_thinking)
        )
    for enable_thinking in (True, False):
        results.append(
            probe_combined_forced_first(client, settings, enable_thinking)
        )
    for enable_thinking in (True, False):
        results.append(
            probe_separated_workflow(client, settings, enable_thinking)
        )

    _print_summary(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
