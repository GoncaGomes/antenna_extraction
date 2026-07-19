from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from antenna_ingest.canonicalization.prompt import (
    CANONICALIZATION_SYSTEM_PROMPT,
    build_canonicalization_user_prompt,
)
from antenna_ingest.canonicalization.schemas import CanonicalDesignRecord
from antenna_ingest.canonicalization.tools import search_evidence
from antenna_ingest.nuextract.client import build_openai_compatible_client
from antenna_ingest.nuextract.raw_extraction import ANTENNA_CANDIDATE_PATH
from antenna_ingest.nuextract.settings import (
    NuExtractSettings,
    load_nuextract_settings,
)
from antenna_ingest.orchestration.schemas import StrictModel
from antenna_ingest.utils.json_io import read_json


SEARCH_EVIDENCE_TOOL = {
    "type": "function",
    "function": {
        "name": "search_evidence",
        "description": (
            "Search the evidence index for the current scientific paper. "
            "Use specific queries to retrieve evidence needed to verify "
            "the final antenna design and its architecture."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Specific evidence search query.",
                },
                "top_k": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 12,
                    "default": 8,
                },
                "context_window": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 2,
                    "default": 1,
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}

CANONICAL_DESIGN_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "canonical_design_record",
        "strict": True,
        "schema": CanonicalDesignRecord.model_json_schema(),
    },
}


class CanonicalizationSearchTrace(StrictModel):
    tool_call_id: str
    query: str
    top_k: int
    context_window: int
    returned_evidence_ids: list[str]


class CanonicalizationAgentResult(StrictModel):
    model: str
    enable_thinking: bool
    raw_response: str
    searches: list[CanonicalizationSearchTrace]
    retrieved_evidence_ids: list[str]


def run_canonicalization_agent(
    run_dir: Path,
    *,
    settings: NuExtractSettings | None = None,
    client: object | None = None,
    max_tool_calls: int = 12,
    enable_thinking: bool = True,
) -> CanonicalizationAgentResult:
    run_dir = Path(run_dir).resolve()
    candidate_path = run_dir / ANTENNA_CANDIDATE_PATH
    if not candidate_path.is_file():
        raise FileNotFoundError(
            f"preliminary antenna candidate does not exist: {candidate_path}"
        )
    candidate = read_json(candidate_path)

    settings = settings or load_nuextract_settings()
    if client is None:
        client = build_openai_compatible_client(
            base_url=settings.skynet_base_url,
            api_key=settings.skynet_api_key.get_secret_value(),
            timeout_seconds=settings.canonicalizer_timeout_seconds,
        )

    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": CANONICALIZATION_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": build_canonicalization_user_prompt(candidate),
        },
    ]
    tool_call_count = 0
    searches: list[CanonicalizationSearchTrace] = []
    retrieved_evidence_ids: list[str] = []
    retrieved_evidence_id_set: set[str] = set()

    while True:
        tool_choice: str | dict[str, Any]
        if tool_call_count == 0:
            tool_choice = {
                "type": "function",
                "function": {"name": "search_evidence"},
            }
        else:
            tool_choice = "auto"
        response = client.chat.completions.create(
            model=settings.canonicalizer_model,
            messages=messages,
            tools=[SEARCH_EVIDENCE_TOOL],
            tool_choice=tool_choice,
            temperature=0.0,
            extra_body={
                "chat_template_kwargs": {
                    "enable_thinking": enable_thinking,
                }
            },
        )
        message = response.choices[0].message
        tool_calls = message.tool_calls or []

        if not tool_calls:
            if not searches:
                raise RuntimeError(
                    "canonicalization agent attempted to finalize before "
                    "retrieving evidence"
                )
            if not retrieved_evidence_ids:
                raise RuntimeError(
                    "canonicalization agent retrieved no evidence before finalizing"
                )
            break

        if tool_call_count + len(tool_calls) > max_tool_calls:
            raise RuntimeError("maximum canonicalization tool-call limit reached")
        tool_call_count += len(tool_calls)

        messages.append(_assistant_tool_call_message(message.content, tool_calls))
        for tool_call in tool_calls:
            if tool_call.function.name != "search_evidence":
                raise ValueError(
                    f"unknown canonicalization tool: {tool_call.function.name}"
                )
            arguments = _parse_tool_arguments(tool_call.function.arguments)
            result = search_evidence(
                run_dir,
                query=arguments["query"],
                top_k=arguments.get("top_k", 8),
                context_window=arguments.get("context_window", 1),
            )
            returned_evidence_ids = [
                item.evidence_id for item in result.results
            ]
            searches.append(
                CanonicalizationSearchTrace(
                    tool_call_id=tool_call.id,
                    query=result.query,
                    top_k=arguments.get("top_k", 8),
                    context_window=arguments.get("context_window", 1),
                    returned_evidence_ids=returned_evidence_ids,
                )
            )
            for evidence_id in returned_evidence_ids:
                if evidence_id not in retrieved_evidence_id_set:
                    retrieved_evidence_id_set.add(evidence_id)
                    retrieved_evidence_ids.append(evidence_id)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result.model_dump_json(),
                }
            )

    finalization_messages = [
        *messages,
        {
            "role": "user",
            "content": (
                "Using only the evidence returned by search_evidence during "
                "this execution, produce the final canonical design record. "
                "Cite only evidence IDs returned during this execution. "
                "Do not call any tools."
            ),
        },
    ]
    final_response = client.chat.completions.create(
        model=settings.canonicalizer_model,
        messages=finalization_messages,
        temperature=0.0,
        response_format=CANONICAL_DESIGN_RESPONSE_FORMAT,
        extra_body={
            "chat_template_kwargs": {
                "enable_thinking": enable_thinking,
            }
        },
    )
    final_message = final_response.choices[0].message
    if final_message.tool_calls:
        raise RuntimeError(
            "canonicalizer returned unexpected tool calls during finalization"
        )
    if not isinstance(final_message.content, str) or not final_message.content.strip():
        raise RuntimeError("canonicalizer returned no final structured response text")
    return CanonicalizationAgentResult(
        model=settings.canonicalizer_model,
        enable_thinking=enable_thinking,
        raw_response=final_message.content,
        searches=searches,
        retrieved_evidence_ids=retrieved_evidence_ids,
    )


def _assistant_tool_call_message(
    content: str | None,
    tool_calls: list[Any],
) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": content,
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


def _parse_tool_arguments(arguments: str) -> dict[str, Any]:
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError as error:
        raise ValueError("canonicalization tool arguments are invalid JSON") from error
    if not isinstance(parsed, dict):
        raise ValueError("canonicalization tool arguments must be a JSON object")
    return parsed
