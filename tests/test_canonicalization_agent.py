from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from antenna_ingest.canonicalization.agent import run_canonicalization_agent
from antenna_ingest.canonicalization.prompt import build_canonicalization_user_prompt
from antenna_ingest.nuextract.raw_extraction import ANTENNA_CANDIDATE_PATH
from antenna_ingest.nuextract.settings import NuExtractSettings
from antenna_ingest.retrieval.index import (
    EVIDENCE_INDEX_PATH,
    EvidenceIndexItem,
    tokenize_text,
    write_jsonl,
)
from antenna_ingest.utils.json_io import write_json


FINAL_RESPONSE = '{"schema_name":"canonical_design_record_v1"}'


def test_model_can_return_final_response_without_tool(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    client = FakeClient([model_response(content=FINAL_RESPONSE)])

    result = run_canonicalization_agent(
        run_dir,
        settings=make_settings(),
        client=client,
    )

    assert result == FINAL_RESPONSE
    assert len(client.completions.calls) == 1


def test_one_search_is_executed_before_final_response(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    client = FakeClient(
        [
            model_response(tool_calls=[tool_call("call_1", query="FR4")]),
            model_response(content=FINAL_RESPONSE),
        ]
    )

    result = run_canonicalization_agent(
        run_dir,
        settings=make_settings(),
        client=client,
    )

    assert result == FINAL_RESPONSE
    second_messages = client.completions.calls[1]["messages"]
    tool_message = second_messages[-1]
    tool_result = json.loads(tool_message["content"])
    assert tool_message["role"] == "tool"
    assert tool_result["results"][0]["evidence_id"] == "block_material"


def test_several_sequential_searches_share_one_conversation(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    client = FakeClient(
        [
            model_response(tool_calls=[tool_call("call_1", query="FR4")]),
            model_response(tool_calls=[tool_call("call_2", query="geometry")]),
            model_response(content=FINAL_RESPONSE),
        ]
    )

    run_canonicalization_agent(
        run_dir,
        settings=make_settings(),
        client=client,
    )

    final_messages = client.completions.calls[2]["messages"]
    assert [message["role"] for message in final_messages] == [
        "system",
        "user",
        "assistant",
        "tool",
        "assistant",
        "tool",
    ]


def test_multiple_tool_calls_in_one_response_are_executed(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    client = FakeClient(
        [
            model_response(
                tool_calls=[
                    tool_call("call_1", query="FR4", top_k=1),
                    tool_call("call_2", query="geometry", context_window=0),
                ]
            ),
            model_response(content=FINAL_RESPONSE),
        ]
    )

    run_canonicalization_agent(
        run_dir,
        settings=make_settings(),
        client=client,
    )

    second_messages = client.completions.calls[1]["messages"]
    assert [message["role"] for message in second_messages[-3:]] == [
        "assistant",
        "tool",
        "tool",
    ]
    assistant_calls = second_messages[-3]["tool_calls"]
    assert [item["id"] for item in assistant_calls] == ["call_1", "call_2"]
    assert assistant_calls[0]["function"]["arguments"] == (
        '{"query": "FR4", "top_k": 1}'
    )


def test_tool_results_use_correct_tool_call_ids(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    client = FakeClient(
        [
            model_response(
                tool_calls=[
                    tool_call("material_call", query="FR4"),
                    tool_call("geometry_call", query="geometry"),
                ]
            ),
            model_response(content=FINAL_RESPONSE),
        ]
    )

    run_canonicalization_agent(
        run_dir,
        settings=make_settings(),
        client=client,
    )

    tool_messages = [
        message
        for message in client.completions.calls[1]["messages"]
        if message["role"] == "tool"
    ]
    assert [message["tool_call_id"] for message in tool_messages] == [
        "material_call",
        "geometry_call",
    ]


def test_unknown_tool_name_raises_clear_error(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    client = FakeClient(
        [model_response(tool_calls=[tool_call("call_1", name="other_tool")])]
    )

    with pytest.raises(ValueError, match="unknown canonicalization tool: other_tool"):
        run_canonicalization_agent(
            run_dir,
            settings=make_settings(),
            client=client,
        )


def test_invalid_json_tool_arguments_raise_clear_error(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    client = FakeClient(
        [
            model_response(
                tool_calls=[tool_call("call_1", arguments="{invalid json")]
            )
        ]
    )

    with pytest.raises(ValueError, match="tool arguments are invalid JSON"):
        run_canonicalization_agent(
            run_dir,
            settings=make_settings(),
            client=client,
        )


def test_maximum_tool_call_limit_is_enforced(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    client = FakeClient(
        [
            model_response(
                tool_calls=[
                    tool_call("call_1", query="FR4"),
                    tool_call("call_2", query="geometry"),
                ]
            )
        ]
    )

    with pytest.raises(
        RuntimeError,
        match="maximum canonicalization tool-call limit reached",
    ):
        run_canonicalization_agent(
            run_dir,
            settings=make_settings(),
            client=client,
            max_tool_calls=1,
        )


def test_missing_candidate_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(
        FileNotFoundError,
        match="preliminary antenna candidate does not exist",
    ):
        run_canonicalization_agent(tmp_path / "missing_run")


def test_configured_canonicalizer_model_is_passed_to_request(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    client = FakeClient([model_response(content=FINAL_RESPONSE)])
    settings = make_settings(model="configured-gemma-model")

    run_canonicalization_agent(run_dir, settings=settings, client=client)

    call = client.completions.calls[0]
    assert call["model"] == "configured-gemma-model"
    assert call["tool_choice"] == "auto"
    assert call["temperature"] == 0.0


def test_user_prompt_contains_candidate_and_target_schema() -> None:
    prompt = build_canonicalization_user_prompt(
        {"paper_title": "Antena não convencional"}
    )

    assert "PRELIMINARY ANTENNA CANDIDATE" in prompt
    assert '"paper_title": "Antena não convencional"' in prompt
    assert "TARGET CANONICAL DESIGN SCHEMA" in prompt
    assert '"canonical_design_record_v1"' in prompt


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


def model_response(
    content: str | None = None,
    tool_calls: list[SimpleNamespace] | None = None,
) -> SimpleNamespace:
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def tool_call(
    call_id: str,
    *,
    name: str = "search_evidence",
    query: str = "test query",
    top_k: int | None = None,
    context_window: int | None = None,
    arguments: str | None = None,
) -> SimpleNamespace:
    if arguments is None:
        values = {"query": query}
        if top_k is not None:
            values["top_k"] = top_k
        if context_window is not None:
            values["context_window"] = context_window
        arguments = json.dumps(values)
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def make_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run"
    write_json(
        run_dir / ANTENNA_CANDIDATE_PATH,
        {
            "paper_title": "Synthetic antenna paper",
            "final_design": {"antenna_type": "printed antenna"},
        },
    )
    items = [
        index_item(
            evidence_id="block_heading",
            order=0,
            kind="heading",
            text="Antenna Design",
            next_id="block_material",
        ),
        index_item(
            evidence_id="block_material",
            order=1,
            kind="paragraph",
            text="The final antenna uses an FR4 substrate of thickness 1.6 mm.",
            previous_id="block_heading",
            next_id="block_figure",
        ),
        index_item(
            evidence_id="block_figure",
            order=2,
            kind="figure_caption",
            text="Figure 1. Geometry of the final antenna.",
            previous_id="block_material",
        ),
    ]
    write_jsonl(run_dir / EVIDENCE_INDEX_PATH, items)
    return run_dir


def index_item(
    evidence_id: str,
    order: int,
    kind: str,
    text: str,
    previous_id: str | None = None,
    next_id: str | None = None,
) -> EvidenceIndexItem:
    tokens = tokenize_text(text)
    return EvidenceIndexItem(
        evidence_id=evidence_id,
        source_type="block",
        source_id=evidence_id,
        page=1,
        kind=kind,
        order=order,
        text=text,
        section="Antenna Design",
        tokens=tokens,
        key_tokens=tokens,
        numbers=["1.6"],
        units=["mm"],
        previous_id=previous_id,
        next_id=next_id,
        source_artifact="parsed/evidence_blocks.jsonl",
    )


def make_settings(model: str = "test-canonicalizer") -> NuExtractSettings:
    return NuExtractSettings(
        _env_file=None,
        SKYNET_BASE_URL="https://example.invalid/v1",
        SKYNET_API_KEY="test-key",
        NUEXTRACT_MODEL="test-nuextract",
        CANONICALIZER_MODEL=model,
        CANONICALIZER_TIMEOUT_SECONDS=30,
    )
