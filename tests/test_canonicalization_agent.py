from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from antenna_ingest.canonicalization.agent import (
    CANONICAL_DESIGN_RESPONSE_FORMAT,
    SEARCH_EVIDENCE_TOOL,
    run_canonicalization_agent,
)
from antenna_ingest.canonicalization.prompt import build_canonicalization_user_prompt
from antenna_ingest.canonicalization.schemas import CanonicalDesignRecord
from antenna_ingest.nuextract.raw_extraction import ANTENNA_CANDIDATE_PATH
from antenna_ingest.nuextract.settings import NuExtractSettings
from antenna_ingest.retrieval.index import (
    EVIDENCE_INDEX_PATH,
    EvidenceIndexItem,
    tokenize_text,
    write_jsonl,
)
from antenna_ingest.utils.json_io import write_json


FINAL_RESPONSE = json.dumps(
    {
        "schema_name": "canonical_design_record_v1",
        "design": {
            "selection_reason": "Selected from the retrieved final design.",
            "evidence_ids": ["block_material"],
        },
        "reconstruction_status": "unknown",
    }
)


def test_finalization_without_search_fails(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    client = FakeClient([model_response(content="retrieval complete")])

    with pytest.raises(
        RuntimeError,
        match="attempted to finalize before retrieving evidence",
    ):
        run_canonicalization_agent(
            run_dir,
            settings=make_settings(),
            client=client,
        )

    assert len(client.completions.calls) == 1


def test_first_retrieval_request_forces_tool_without_response_format(
    tmp_path: Path,
) -> None:
    run_dir = make_run(tmp_path)
    client = FakeClient([model_response(content="retrieval complete")])

    with pytest.raises(RuntimeError, match="before retrieving evidence"):
        run_canonicalization_agent(
            run_dir,
            settings=make_settings(),
            client=client,
        )

    call = client.completions.calls[0]
    assert call["tools"] == [SEARCH_EVIDENCE_TOOL]
    assert call["tool_choice"] == {
        "type": "function",
        "function": {"name": "search_evidence"},
    }
    assert "response_format" not in call


def test_later_retrieval_and_finalization_requests_are_separated(
    tmp_path: Path,
) -> None:
    run_dir = make_run(tmp_path)
    client = FakeClient(successful_responses())

    run_canonicalization_agent(
        run_dir,
        settings=make_settings(),
        client=client,
    )

    first_call, retrieval_end_call, final_call = client.completions.calls
    assert first_call["tool_choice"]["function"]["name"] == "search_evidence"
    assert retrieval_end_call["tools"] == [SEARCH_EVIDENCE_TOOL]
    assert retrieval_end_call["tool_choice"] == "auto"
    assert "response_format" not in retrieval_end_call
    assert final_call["response_format"] == CANONICAL_DESIGN_RESPONSE_FORMAT
    assert "tools" not in final_call
    assert "tool_choice" not in final_call


def test_finalization_preserves_tool_history_and_ignores_retrieval_text(
    tmp_path: Path,
) -> None:
    run_dir = make_run(tmp_path)
    retrieval_text = "I have enough evidence now."
    client = FakeClient(
        [
            model_response(tool_calls=[tool_call("call_1", query="FR4")]),
            model_response(content=retrieval_text),
            model_response(content=FINAL_RESPONSE),
        ]
    )

    result = run_canonicalization_agent(
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
        "user",
    ]
    assert final_messages[2]["tool_calls"][0]["id"] == "call_1"
    assert final_messages[3]["tool_call_id"] == "call_1"
    assert retrieval_text not in [message.get("content") for message in final_messages]
    assert "Using only the evidence" in final_messages[-1]["content"]
    assert result.raw_response == FINAL_RESPONSE
    assert result.raw_response != retrieval_text


def test_one_search_is_executed_before_final_response(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    client = FakeClient(successful_responses())

    result = run_canonicalization_agent(
        run_dir,
        settings=make_settings(),
        client=client,
    )

    assert result.raw_response == FINAL_RESPONSE
    assert result.model == "test-canonicalizer"
    assert result.enable_thinking is True
    assert len(result.searches) == 1
    assert result.searches[0].tool_call_id == "call_1"
    assert result.searches[0].query == "FR4"
    assert result.searches[0].top_k == 8
    assert result.searches[0].context_window == 1
    assert result.searches[0].returned_evidence_ids
    assert result.retrieved_evidence_ids == result.searches[0].returned_evidence_ids

    tool_message = client.completions.calls[1]["messages"][-1]
    tool_result = json.loads(tool_message["content"])
    assert tool_message["role"] == "tool"
    assert tool_result["results"][0]["evidence_id"] == "block_material"
    record = CanonicalDesignRecord.model_validate_json(result.raw_response)
    assert record.design.evidence_ids == ["block_material"]


def test_several_searches_collect_ordered_deduplicated_evidence(
    tmp_path: Path,
) -> None:
    run_dir = make_run(tmp_path)
    client = FakeClient(
        [
            model_response(tool_calls=[tool_call("call_1", query="FR4")]),
            model_response(tool_calls=[tool_call("call_2", query="geometry")]),
            model_response(content="retrieval complete"),
            model_response(content=FINAL_RESPONSE),
        ]
    )

    result = run_canonicalization_agent(
        run_dir,
        settings=make_settings(),
        client=client,
    )

    final_messages = client.completions.calls[3]["messages"]
    assert [message["role"] for message in final_messages] == [
        "system",
        "user",
        "assistant",
        "tool",
        "assistant",
        "tool",
        "user",
    ]
    returned_ids = [
        evidence_id
        for search in result.searches
        for evidence_id in search.returned_evidence_ids
    ]
    assert len(result.searches) == 2
    assert result.retrieved_evidence_ids == list(dict.fromkeys(returned_ids))
    assert len(result.retrieved_evidence_ids) < len(returned_ids)


def test_finalization_after_only_empty_searches_fails(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    client = FakeClient(
        [
            model_response(
                tool_calls=[tool_call("call_1", query="no_match_xyz_123")]
            ),
            model_response(content="retrieval complete"),
        ]
    )

    with pytest.raises(
        RuntimeError,
        match="retrieved no evidence before finalizing",
    ):
        run_canonicalization_agent(
            run_dir,
            settings=make_settings(),
            client=client,
        )

    assert len(client.completions.calls) == 2


def test_multiple_tool_calls_are_preserved_with_matching_results(
    tmp_path: Path,
) -> None:
    run_dir = make_run(tmp_path)
    client = FakeClient(
        [
            model_response(
                tool_calls=[
                    tool_call("material_call", query="FR4", top_k=1),
                    tool_call(
                        "geometry_call",
                        query="geometry",
                        context_window=0,
                    ),
                ]
            ),
            model_response(content="retrieval complete"),
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
    assert [item["id"] for item in assistant_calls] == [
        "material_call",
        "geometry_call",
    ]
    assert assistant_calls[0]["function"]["arguments"] == (
        '{"query": "FR4", "top_k": 1}'
    )
    assert [message["tool_call_id"] for message in second_messages[-2:]] == [
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


def test_empty_final_structured_content_fails(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    client = FakeClient(
        [
            model_response(tool_calls=[tool_call("call_1", query="FR4")]),
            model_response(content="retrieval complete"),
            model_response(content="  "),
        ]
    )

    with pytest.raises(
        RuntimeError,
        match="no final structured response text",
    ):
        run_canonicalization_agent(
            run_dir,
            settings=make_settings(),
            client=client,
        )


def test_unexpected_final_tool_call_fails(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    client = FakeClient(
        [
            model_response(tool_calls=[tool_call("call_1", query="FR4")]),
            model_response(content="retrieval complete"),
            model_response(tool_calls=[tool_call("unexpected")]),
        ]
    )

    with pytest.raises(
        RuntimeError,
        match="unexpected tool calls during finalization",
    ):
        run_canonicalization_agent(
            run_dir,
            settings=make_settings(),
            client=client,
        )


@pytest.mark.parametrize("enable_thinking", [True, False])
def test_thinking_mode_is_sent_to_every_model_request(
    tmp_path: Path,
    enable_thinking: bool,
) -> None:
    run_dir = make_run(tmp_path)
    client = FakeClient(successful_responses())

    run_canonicalization_agent(
        run_dir,
        settings=make_settings(),
        client=client,
        enable_thinking=enable_thinking,
    )

    assert len(client.completions.calls) == 3
    assert all(
        call["extra_body"]
        == {"chat_template_kwargs": {"enable_thinking": enable_thinking}}
        for call in client.completions.calls
    )


def test_configured_model_is_sent_to_every_request(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    client = FakeClient(successful_responses())
    settings = make_settings(model="configured-gemma-model")

    run_canonicalization_agent(run_dir, settings=settings, client=client)

    assert all(
        call["model"] == "configured-gemma-model"
        for call in client.completions.calls
    )
    assert all(call["temperature"] == 0.0 for call in client.completions.calls)


def test_missing_candidate_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(
        FileNotFoundError,
        match="preliminary antenna candidate does not exist",
    ):
        run_canonicalization_agent(tmp_path / "missing_run")


def test_user_prompt_contains_candidate_and_target_schema() -> None:
    prompt = build_canonicalization_user_prompt(
        {"paper_title": "Antena nao convencional"}
    )

    assert "PRELIMINARY ANTENNA CANDIDATE" in prompt
    assert '"paper_title": "Antena nao convencional"' in prompt
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


def successful_responses() -> list[SimpleNamespace]:
    return [
        model_response(tool_calls=[tool_call("call_1", query="FR4")]),
        model_response(content="retrieval complete"),
        model_response(content=FINAL_RESPONSE),
    ]


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
