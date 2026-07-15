from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from antenna_ingest.canonicalization.canonicalize import (
    run_validated_canonicalization,
)
from antenna_ingest.canonicalization.schemas import CanonicalDesignRecord
from antenna_ingest.nuextract.raw_extraction import ANTENNA_CANDIDATE_PATH
from antenna_ingest.nuextract.settings import NuExtractSettings
from antenna_ingest.retrieval.index import (
    EVIDENCE_INDEX_PATH,
    EvidenceIndexItem,
    write_jsonl,
)
from antenna_ingest.utils.json_io import write_json


def test_valid_final_output_returns_canonical_design_record(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    client = FakeClient(minimal_response())

    record, report = run_validated_canonicalization(
        run_dir,
        settings=make_settings(),
        client=client,
    )

    assert isinstance(record, CanonicalDesignRecord)
    assert report.valid is True
    assert report.referenced_evidence_count == 1


def test_validation_report_contains_correct_counts(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    client = FakeClient(counted_response())

    _record, report = run_validated_canonicalization(
        run_dir,
        settings=make_settings(),
        client=client,
    )

    assert report.object_count == 2
    assert report.material_count == 1
    assert report.relationship_count == 1
    assert report.excitation_count == 1
    assert report.critical_missing_information_count == 1
    assert report.unresolved_conflict_count == 1


def test_malformed_json_fails_without_repair(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    client = FakeClient('{"schema_name": invalid')

    with pytest.raises(ValidationError):
        run_validated_canonicalization(
            run_dir,
            settings=make_settings(),
            client=client,
        )


def test_schema_invalid_json_fails(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    client = FakeClient('{"schema_name":"canonical_design_record_v1"}')

    with pytest.raises(ValidationError):
        run_validated_canonicalization(
            run_dir,
            settings=make_settings(),
            client=client,
        )


def test_unknown_evidence_id_fails_explicitly(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    response = minimal_record_data()
    response["design"]["evidence_ids"] = ["invented_evidence"]
    client = FakeClient(json.dumps(response))

    with pytest.raises(
        ValueError,
        match=(
            "canonical design references unknown evidence IDs: "
            "invented_evidence"
        ),
    ):
        run_validated_canonicalization(
            run_dir,
            settings=make_settings(),
            client=client,
        )


def test_exact_valid_evidence_ids_pass(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    response = minimal_record_data()
    response["reported_results"] = [
        {
            "metric": "resonant frequency",
            "result_source": "simulated",
            "value": 2.45,
            "unit": "GHz",
            "evidence_ids": ["table_dimensions"],
        }
    ]
    client = FakeClient(json.dumps(response))

    _record, report = run_validated_canonicalization(
        run_dir,
        settings=make_settings(),
        client=client,
    )

    assert report.valid is True
    assert report.referenced_evidence_count == 2
    assert report.unknown_evidence_ids == []


def test_agent_parameters_are_forwarded(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = make_run(tmp_path)
    settings = make_settings(model="forwarded-model")
    client = object()
    captured = {}

    def fake_agent(
        received_run_dir,
        *,
        settings,
        client,
        max_tool_calls,
        enable_thinking,
    ) -> str:
        captured.update(
            {
                "run_dir": received_run_dir,
                "settings": settings,
                "client": client,
                "max_tool_calls": max_tool_calls,
                "enable_thinking": enable_thinking,
            }
        )
        return minimal_response()

    monkeypatch.setattr(
        "antenna_ingest.canonicalization.canonicalize.run_canonicalization_agent",
        fake_agent,
    )

    run_validated_canonicalization(
        run_dir,
        settings=settings,
        client=client,
        max_tool_calls=7,
        enable_thinking=False,
    )

    assert captured == {
        "run_dir": run_dir,
        "settings": settings,
        "client": client,
        "max_tool_calls": 7,
        "enable_thinking": False,
    }


class FakeClient:
    def __init__(self, response_text: str) -> None:
        self.completions = FakeCompletions(response_text)
        self.chat = SimpleNamespace(completions=self.completions)


class FakeCompletions:
    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.calls: list[dict] = []

    def create(self, **kwargs) -> SimpleNamespace:
        self.calls.append(kwargs)
        message = SimpleNamespace(content=self.response_text, tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def make_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run"
    write_json(
        run_dir / ANTENNA_CANDIDATE_PATH,
        {"paper_title": "Synthetic antenna paper"},
    )
    items = [
        evidence_item("block_design", 0),
        evidence_item("table_dimensions", 1),
    ]
    write_jsonl(run_dir / EVIDENCE_INDEX_PATH, items)
    return run_dir


def evidence_item(evidence_id: str, order: int) -> EvidenceIndexItem:
    return EvidenceIndexItem(
        evidence_id=evidence_id,
        source_type="block",
        source_id=evidence_id,
        page=1,
        kind="paragraph",
        order=order,
        text=f"Evidence for {evidence_id}.",
        source_artifact="parsed/evidence_blocks.jsonl",
    )


def minimal_response() -> str:
    return json.dumps(minimal_record_data())


def minimal_record_data() -> dict:
    return {
        "schema_name": "canonical_design_record_v1",
        "design": {
            "selection_reason": "Selected from the reported final design.",
            "evidence_ids": ["block_design"],
        },
        "reconstruction_status": "unknown",
    }


def counted_response() -> str:
    data = minimal_record_data()
    data.update(
        {
            "materials": [
                {
                    "material_id": "copper",
                    "name": "Copper",
                    "evidence_ids": ["block_design"],
                }
            ],
            "objects": [
                {
                    "object_id": "radiator",
                    "role": "radiator",
                    "physical_form": "sheet",
                    "material_id": "copper",
                    "evidence_ids": ["block_design"],
                },
                {
                    "object_id": "feed",
                    "role": "feedline",
                    "physical_form": "sheet",
                    "material_id": "copper",
                    "evidence_ids": ["block_design"],
                },
            ],
            "relationships": [
                {
                    "subject_id": "feed",
                    "relation": "connected_to",
                    "object_id": "radiator",
                    "evidence_ids": ["block_design"],
                }
            ],
            "excitations": [
                {
                    "excitation_id": "port_1",
                    "excitation_type": "lumped port",
                    "target_object_ids": ["feed", "radiator"],
                    "evidence_ids": ["block_design"],
                }
            ],
            "missing_information": [
                {
                    "field": "conductor thickness",
                    "severity": "critical",
                    "reason": "Not reported.",
                    "related_object_ids": ["radiator"],
                }
            ],
            "conflicts": [
                {
                    "field": "feed width",
                    "options": [
                        {
                            "raw_value": "2 mm",
                            "evidence_ids": ["block_design"],
                        },
                        {
                            "raw_value": "3 mm",
                            "evidence_ids": ["table_dimensions"],
                        },
                    ],
                    "status": "unresolved",
                }
            ],
        }
    )
    return json.dumps(data)


def make_settings(model: str = "test-canonicalizer") -> NuExtractSettings:
    return NuExtractSettings(
        _env_file=None,
        SKYNET_BASE_URL="https://example.invalid/v1",
        SKYNET_API_KEY="test-key",
        NUEXTRACT_MODEL="test-nuextract",
        CANONICALIZER_MODEL=model,
        CANONICALIZER_TIMEOUT_SECONDS=30,
    )
