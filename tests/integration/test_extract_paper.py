from __future__ import annotations

import ast
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import fitz
import pytest
from pydantic import SecretStr, ValidationError

from antenna_ingest.contracts.paper_extraction import PaperExtraction
from antenna_ingest.extraction import full_document
from antenna_ingest.extraction import nuextract_contract
from antenna_ingest.extraction.full_document import (
    DOCUMENT_CONTEXT_MESSAGE,
    EXTRACTION_REPORT_PATH,
    EXTRACTION_VALIDATION_PATH,
    NUEXTRACT_INSTRUCTIONS,
    PAPER_EXTRACTION_PATH,
    RAW_RESPONSE_PATH,
    REQUEST_METADATA_PATH,
    extract_paper_from_run,
)
from antenna_ingest.extraction.nuextract_contract import (
    NuExtractPaperExtraction,
    build_nuextract_template,
)
from antenna_ingest.orchestration.runs import create_run
from antenna_ingest.orchestration.schemas import RunManifest
from antenna_ingest.rendering import render_run_pages
from antenna_ingest.settings import AntennaIngestSettings
from antenna_ingest.utils.json_io import read_json


FIXTURE_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "contracts"
    / "minimal_paper_extraction.json"
)


class FakeCompletions:
    def __init__(
        self,
        responses: list[str] | None = None,
        error: Exception | None = None,
        finish_reason: str = "stop",
    ):
        self.responses = list(responses or [])
        self.error = error
        self.finish_reason = finish_reason
        self.calls: list[dict] = []
        self.on_create = None

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.on_create is not None:
            self.on_create()
        if self.error is not None:
            raise self.error
        content = self.responses.pop(0)
        return SimpleNamespace(
            id=f"response-{len(self.calls)}",
            choices=[
                SimpleNamespace(
                    finish_reason=self.finish_reason,
                    message=SimpleNamespace(content=content),
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=101,
                completion_tokens=202,
                total_tokens=303,
            ),
        )


class FakeClient:
    def __init__(
        self,
        responses: list[str] | None = None,
        error: Exception | None = None,
        finish_reason: str = "stop",
    ):
        self.completions = FakeCompletions(responses, error, finish_reason)
        self.chat = SimpleNamespace(completions=self.completions)


@pytest.mark.parametrize("enable_thinking", [True, False])
def test_full_document_request_is_ordered_strict_and_traceable(
    tmp_path: Path,
    enable_thinking: bool,
) -> None:
    run_dir = _rendered_run(tmp_path)
    response_data = _valid_extraction(run_dir)
    response_data["observations"][1]["reported_impedance"] = {
        "value": "50",
        "unit": "ohm",
        "qualifier": None,
        "legibility": "clear",
    }
    response_data["setups"][0]["equipment"] = ["inactive VNA"]
    response_data["results"][0]["representation"]["image_axes"] = [
        {"name": "inactive axis", "unit": None}
    ]
    raw_response = json.dumps(response_data, ensure_ascii=False)
    client = FakeClient([raw_response])
    metadata_seen_before_call = []

    def record_pre_call_metadata() -> None:
        metadata_seen_before_call.append(read_json(run_dir / REQUEST_METADATA_PATH))

    client.completions.on_create = record_pre_call_metadata

    extraction = extract_paper_from_run(
        run_dir,
        enable_thinking=enable_thinking,
        settings=_settings(),
        client=client,
    )

    assert extraction.document.page_count == 2
    assert len(client.completions.calls) == 1
    request = client.completions.calls[0]
    expected_temperature = 0.6 if enable_thinking else 0.2
    assert request["temperature"] == expected_temperature
    assert request["max_tokens"] == 12345
    template_json = request["extra_body"]["chat_template_kwargs"]["template"]
    assert request["extra_body"] == {
        "chat_template_kwargs": {
            "template": template_json,
            "instructions": NUEXTRACT_INSTRUCTIONS,
            "enable_thinking": enable_thinking,
        }
    }
    assert json.loads(template_json) == build_nuextract_template()
    assert request["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "nuextract_paper_extraction",
            "strict": True,
            "schema": NuExtractPaperExtraction.model_json_schema(mode="validation"),
        },
    }

    messages = request["messages"]
    assert len(messages) == 1
    content = messages[0]["content"]
    assert [item["text"] for item in content if item["type"] == "text"][1:] == [
        "PDF_INPUT_PAGE=1",
        "PDF_INPUT_PAGE=2",
    ]
    assert [item["type"] for item in content] == [
        "text",
        "text",
        "image_url",
        "text",
        "image_url",
    ]
    prompt_text = content[0]["text"]
    assert prompt_text == DOCUMENT_CONTEXT_MESSAGE
    assert all(
        NUEXTRACT_INSTRUCTIONS not in item.get("text", "")
        for item in content
        if item["type"] == "text"
    )

    manifest_before = RunManifest.model_validate(read_json(run_dir / "manifest.json"))
    assert manifest_before.document_id not in prompt_text
    assert manifest_before.input_sha256 not in prompt_text
    assert Path(manifest_before.input_file).name not in prompt_text
    image_urls = [
        item["image_url"]["url"] for item in content if item["type"] == "image_url"
    ]
    assert len(image_urls) == 2
    assert len(set(image_urls)) == 2

    metadata_path = run_dir / REQUEST_METADATA_PATH
    metadata = read_json(metadata_path)
    metadata_text = metadata_path.read_text(encoding="utf-8")
    assert metadata["model"] == "test-extractor"
    assert metadata["thinking_enabled"] is enable_thinking
    assert metadata["temperature"] == expected_temperature
    assert metadata["page_count"] == 2
    assert [page["page_number"] for page in metadata["pages"]] == [1, 2]
    assert all(len(page["sha256"]) == 64 for page in metadata["pages"])
    assert len(metadata["prompt_hash"]) == 64
    assert len(metadata["template_hash"]) == 64
    assert len(metadata["schema_hash"]) == 64
    assert (
        metadata["prompt_hash"]
        == hashlib.sha256(NUEXTRACT_INSTRUCTIONS.encode("utf-8")).hexdigest()
    )
    assert (
        metadata["template_hash"]
        == hashlib.sha256(template_json.encode("utf-8")).hexdigest()
    )
    rendered_schema = json.dumps(
        NuExtractPaperExtraction.model_json_schema(mode="validation"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert (
        metadata["schema_hash"]
        == hashlib.sha256(rendered_schema.encode("utf-8")).hexdigest()
    )
    assert metadata["request_started_at"]
    assert metadata["request_completed_at"]
    assert metadata["response_id"] == "response-1"
    assert "data:image" not in metadata_text
    assert "api-secret" not in metadata_text
    assert "url-secret" not in metadata_text
    assert "endpoint-user:endpoint-password" not in metadata_text
    assert metadata["endpoint"]["timeout_seconds"] == 240
    assert metadata["max_output_tokens"] == 12345
    assert template_json not in metadata_text
    assert metadata_seen_before_call[0]["request_completed_at"] is None
    assert metadata_seen_before_call[0]["response_id"] is None
    assert metadata_seen_before_call[0]["temperature"] == expected_temperature
    assert metadata_seen_before_call[0]["max_output_tokens"] == 12345
    assert metadata_seen_before_call[0]["prompt_hash"] == metadata["prompt_hash"]
    assert metadata_seen_before_call[0]["template_hash"] == metadata["template_hash"]
    assert metadata_seen_before_call[0]["schema_hash"] == metadata["schema_hash"]

    assert (run_dir / RAW_RESPONSE_PATH).read_text(encoding="utf-8") == raw_response
    assert (run_dir / PAPER_EXTRACTION_PATH).is_file()
    assert (run_dir / EXTRACTION_REPORT_PATH).is_file()
    assert (run_dir / EXTRACTION_VALIDATION_PATH).is_file()
    manifest = RunManifest.model_validate(read_json(run_dir / "manifest.json"))
    assert manifest.phases["paper_extraction"].status == "completed"
    assert manifest.phases["paper_extraction"].attempt == 1
    assert manifest.phases["paper_extraction"].prompt_hash == metadata["prompt_hash"]
    assert manifest.phases["paper_extraction"].schema_hash == metadata["schema_hash"]
    persisted = PaperExtraction.model_validate(
        read_json(run_dir / PAPER_EXTRACTION_PATH)
    )
    raw_data = json.loads(raw_response)
    raw_document = raw_data["document"]
    for deterministic_field in (
        "schema_name",
        "schema_version",
        "pages",
        "architecture_page_refs",
    ):
        assert deterministic_field not in raw_data
    assert set(raw_document) == {"title", "doi"}
    assert persisted.document.document_id == manifest.document_id
    assert persisted.document.page_count == 2
    assert persisted.document.source_filename == Path(manifest.input_file).name
    assert persisted.document.sha256 == manifest.input_sha256
    assert persisted.document.title == raw_document["title"]
    assert persisted.document.doi == raw_document["doi"]
    assert [page.model_dump(mode="json") for page in persisted.pages] == [
        {"page_number": 1, "visible_label": None},
        {"page_number": 2, "visible_label": None},
    ]
    assert persisted.architecture_page_refs == [1, 2]
    assert "reported_impedance" not in persisted.parameter_observations[0].model_dump(
        mode="json"
    )
    assert "equipment" not in persisted.setups[0].model_dump(mode="json")
    assert "image_axes" not in persisted.results[0].representation.model_dump(
        mode="json"
    )
    validation_report = read_json(run_dir / EXTRACTION_VALIDATION_PATH)
    assert (
        validation_report["deterministic_context_source"]
        == "manifest_and_render_report"
    )
    assert validation_report["deterministic_document_fields"] == [
        "document_id",
        "page_count",
        "source_filename",
        "sha256",
        "pages",
    ]


def test_raw_response_survives_malformed_json_and_phase_fails(tmp_path: Path) -> None:
    run_dir = _rendered_run(tmp_path)
    raw_response = "{malformed JSON"
    client = FakeClient([raw_response])

    with pytest.raises(json.JSONDecodeError):
        extract_paper_from_run(
            run_dir,
            enable_thinking=False,
            settings=_settings(),
            client=client,
        )

    assert len(client.completions.calls) == 1
    assert (run_dir / RAW_RESPONSE_PATH).read_text(encoding="utf-8") == raw_response
    failure, manifest = _failure_and_manifest(run_dir)
    assert failure["substage"] == "response_parsing"
    assert failure["response_artifact"] == RAW_RESPONSE_PATH
    assert RAW_RESPONSE_PATH in failure["partial_artifacts"]
    assert manifest.phases["paper_extraction"].status == "failed"
    assert manifest.phases["paper_extraction"].status != "running"


def test_truncated_response_fails_before_parsing_and_preserves_diagnostics(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = _rendered_run(tmp_path)
    raw_response = "{truncated response"
    client = FakeClient([raw_response], finish_reason="length")

    def forbid_json_parsing(*args, **kwargs):
        raise AssertionError("JSON parsing must not run for a truncated response")

    def forbid_schema_validation(*args, **kwargs):
        raise AssertionError("schema validation must not run for a truncated response")

    def install_parsing_guards() -> None:
        monkeypatch.setattr(
            full_document,
            "json",
            SimpleNamespace(loads=forbid_json_parsing),
        )

    client.completions.on_create = install_parsing_guards
    monkeypatch.setattr(
        full_document.NuExtractPaperExtraction,
        "model_validate",
        forbid_schema_validation,
    )

    with pytest.raises(
        RuntimeError,
        match="reached the output-token limit and is incomplete",
    ):
        extract_paper_from_run(
            run_dir,
            enable_thinking=False,
            settings=_settings(),
            client=client,
        )

    assert len(client.completions.calls) == 1
    assert (run_dir / RAW_RESPONSE_PATH).read_text(encoding="utf-8") == raw_response
    metadata = read_json(run_dir / REQUEST_METADATA_PATH)
    assert metadata["request_completed_at"] is not None
    assert metadata["response_id"] == "response-1"
    assert metadata["finish_reason"] == "length"
    assert metadata["usage"] == {
        "prompt_tokens": 101,
        "completion_tokens": 202,
        "total_tokens": 303,
    }

    failure, manifest = _failure_and_manifest(run_dir)
    assert failure["substage"] == "response_truncation"
    assert failure["response_artifact"] == RAW_RESPONSE_PATH
    assert RAW_RESPONSE_PATH in failure["partial_artifacts"]
    assert REQUEST_METADATA_PATH in failure["partial_artifacts"]
    assert "output-token limit" in failure["message"]
    assert manifest.phases["paper_extraction"].status == "failed"
    assert not (run_dir / PAPER_EXTRACTION_PATH).exists()


@pytest.mark.parametrize(
    ("failure_kind", "expected_substage"),
    [
        ("model_schema", "model_response_validation"),
        ("normalization", "deterministic_normalization"),
    ],
)
def test_model_validation_and_normalization_errors_are_inspectable(
    tmp_path: Path,
    failure_kind: str,
    expected_substage: str,
) -> None:
    run_dir = _rendered_run(tmp_path)
    response_data = _valid_extraction(run_dir)
    if failure_kind == "model_schema":
        response_data["unexpected"] = "forbidden"
    else:
        response_data["designs"][1]["parent_design_id"] = "unknown_design"
    raw_response = json.dumps(response_data)
    client = FakeClient([raw_response])

    with pytest.raises(ValidationError):
        extract_paper_from_run(
            run_dir,
            enable_thinking=True,
            settings=_settings(),
            client=client,
        )

    failure, manifest = _failure_and_manifest(run_dir)
    assert failure["substage"] == expected_substage
    assert failure["response_artifact"] == RAW_RESPONSE_PATH
    assert (run_dir / RAW_RESPONSE_PATH).read_text(encoding="utf-8") == raw_response
    assert not (run_dir / PAPER_EXTRACTION_PATH).exists()
    assert manifest.phases["paper_extraction"].status == "failed"


def test_final_validation_failure_preserves_raw_response(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = _rendered_run(tmp_path)
    response_data = _valid_extraction(run_dir)
    raw_response = json.dumps(response_data)
    client = FakeClient([raw_response])

    def fail_final_validation(*args, **kwargs) -> None:
        raise ValueError("forced final validation failure")

    monkeypatch.setattr(
        full_document,
        "_validate_extraction_context",
        fail_final_validation,
    )

    with pytest.raises(ValueError, match="forced final validation failure"):
        extract_paper_from_run(
            run_dir,
            enable_thinking=False,
            settings=_settings(),
            client=client,
        )

    failure, manifest = _failure_and_manifest(run_dir)
    assert failure["substage"] == "final_validation"
    assert failure["response_artifact"] == RAW_RESPONSE_PATH
    assert (run_dir / RAW_RESPONSE_PATH).read_text(encoding="utf-8") == raw_response
    assert manifest.phases["paper_extraction"].status == "failed"


def test_document_context_is_constructed_without_mutating_raw_response(
    tmp_path: Path,
) -> None:
    run_dir = _rendered_run(tmp_path)
    response_data = _valid_extraction(run_dir)
    raw_response = json.dumps(response_data)
    client = FakeClient([raw_response])

    extraction = extract_paper_from_run(
        run_dir,
        enable_thinking=False,
        settings=_settings(),
        client=client,
    )

    manifest = RunManifest.model_validate(read_json(run_dir / "manifest.json"))
    persisted_extraction = read_json(run_dir / PAPER_EXTRACTION_PATH)
    persisted_raw = json.loads(
        (run_dir / RAW_RESPONSE_PATH).read_text(encoding="utf-8")
    )
    validation_report = read_json(run_dir / EXTRACTION_VALIDATION_PATH)

    assert len(client.completions.calls) == 1
    assert extraction.document.source_filename == Path(manifest.input_file).name
    assert extraction.document.sha256 == manifest.input_sha256
    assert (
        persisted_extraction["document"]["source_filename"]
        == Path(manifest.input_file).name
    )
    assert persisted_extraction["document"]["sha256"] == manifest.input_sha256
    assert persisted_raw["document"] == {
        "title": "Synthetic antenna paper",
        "doi": None,
    }
    assert (
        validation_report["deterministic_context_source"]
        == "manifest_and_render_report"
    )
    assert validation_report["deterministic_document_fields"] == [
        "document_id",
        "page_count",
        "source_filename",
        "sha256",
        "pages",
    ]


def test_extraction_requires_completed_page_rendering_without_model_call(
    tmp_path: Path,
) -> None:
    input_pdf = tmp_path / "article.pdf"
    document = fitz.open()
    try:
        document.new_page()
        document.save(input_pdf)
    finally:
        document.close()
    context = create_run(input_pdf, runs_root=tmp_path / "runs")
    client = FakeClient(["unused"])

    with pytest.raises(ValueError, match="page_rendering phase must be completed"):
        extract_paper_from_run(
            context.run_dir,
            enable_thinking=True,
            settings=_settings(),
            client=client,
        )

    manifest = RunManifest.model_validate(read_json(context.run_dir / "manifest.json"))
    assert len(client.completions.calls) == 0
    assert manifest.phases["paper_extraction"].status == "pending"


def test_dropped_template_branch_fails_before_model_call(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = _rendered_run(tmp_path)
    client = FakeClient(["unused"])

    monkeypatch.setattr(
        nuextract_contract,
        "convert_json_schema_to_nuextract_template",
        lambda schema: (
            {},
            [{"path": "$.results", "error": "unsupported branch"}],
            [],
        ),
    )

    with pytest.raises(
        ValueError,
        match="NuExtract template conversion dropped schema branches",
    ):
        extract_paper_from_run(
            run_dir,
            enable_thinking=False,
            settings=_settings(),
            client=client,
        )

    manifest = RunManifest.model_validate(read_json(run_dir / "manifest.json"))
    assert len(client.completions.calls) == 0
    assert manifest.phases["paper_extraction"].status == "pending"
    assert not (run_dir / REQUEST_METADATA_PATH).exists()


def test_request_failure_is_redacted_and_never_retried(tmp_path: Path) -> None:
    run_dir = _rendered_run(tmp_path)
    client = FakeClient(error=RuntimeError("api_key=request-secret"))

    with pytest.raises(RuntimeError, match="request-secret"):
        extract_paper_from_run(
            run_dir,
            enable_thinking=False,
            settings=_settings(),
            client=client,
        )

    assert len(client.completions.calls) == 1
    assert (run_dir / REQUEST_METADATA_PATH).is_file()
    assert not (run_dir / RAW_RESPONSE_PATH).exists()
    failure, manifest = _failure_and_manifest(run_dir)
    persisted_failure = run_dir / manifest.phases["paper_extraction"].failure_reference
    assert "request-secret" not in persisted_failure.read_text(encoding="utf-8")
    assert "[redacted]" in failure["message"]
    assert manifest.phases["paper_extraction"].status == "failed"


def test_force_replaces_outputs_without_duplicate_manifest_artifacts(
    tmp_path: Path,
) -> None:
    run_dir = _rendered_run(tmp_path)
    raw_response = json.dumps(_valid_extraction(run_dir))
    first_client = FakeClient([raw_response])
    second_client = FakeClient([raw_response])
    settings = _settings()

    extract_paper_from_run(
        run_dir,
        enable_thinking=True,
        settings=settings,
        client=first_client,
    )
    extract_paper_from_run(
        run_dir,
        enable_thinking=False,
        force=True,
        settings=settings,
        client=second_client,
    )

    manifest = RunManifest.model_validate(read_json(run_dir / "manifest.json"))
    assert manifest.phases["paper_extraction"].status == "completed"
    assert manifest.phases["paper_extraction"].attempt == 2
    extraction_artifact_names = {
        "nuextract3_request_metadata",
        "nuextract3_raw_response",
        "paper_extraction",
        "extraction_report",
        "extraction_validation",
    }
    for artifact_name in extraction_artifact_names:
        assert [artifact.name for artifact in manifest.artifacts].count(
            artifact_name
        ) == 1
    assert len(first_client.completions.calls) == 1
    assert len(second_client.completions.calls) == 1
    assert read_json(run_dir / REQUEST_METADATA_PATH)["thinking_enabled"] is False


def test_extraction_module_has_no_legacy_or_page_selection_dependency() -> None:
    source_path = Path(full_document.__file__)
    source = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_modules = {
        node.module
        for node in ast.walk(source)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    disallowed_fragments = {
        "markdown",
        "retrieval",
        "canonicalization",
        "candidate",
        "page_selection",
    }

    assert not any(
        fragment in module
        for module in imported_modules
        for fragment in disallowed_fragments
    )
    assert "render_run_pages" not in source_path.read_text(encoding="utf-8")


def _rendered_run(tmp_path: Path) -> Path:
    input_pdf = tmp_path / "article.pdf"
    document = fitz.open()
    try:
        for page_number in (1, 2):
            page = document.new_page()
            page.insert_text((72, 72), f"Unique test page {page_number}")
        document.save(input_pdf)
    finally:
        document.close()
    context = create_run(input_pdf, runs_root=tmp_path / "runs")
    render_run_pages(context.run_dir, dpi=72)
    return context.run_dir


def _valid_extraction(run_dir: Path) -> dict:
    data = read_json(FIXTURE_PATH)
    return _replace_evidence_ids_with_inline_evidence(data)


def _replace_evidence_ids_with_inline_evidence(data: dict) -> dict:
    response = deepcopy(data)
    response.pop("schema_name")
    response.pop("schema_version")
    response.pop("pages")
    response.pop("architecture_page_refs")
    response["document"] = {
        "title": response["document"]["title"],
        "doi": response["document"]["doi"],
    }
    catalog = {
        item["evidence_id"]: {
            key: value for key, value in item.items() if key != "evidence_id"
        }
        for item in response.pop("evidence_catalog")
    }

    collections = (
        "designs",
        "setups",
        "results",
        "derivations",
        "conflicts",
        "missing_information",
    )
    for collection_name in collections:
        for record in response[collection_name]:
            record["evidence"] = [
                deepcopy(catalog[evidence_id])
                for evidence_id in record.pop("evidence_ids")
            ]

    observations = []
    for collection_name, kind in (
        ("material_observations", "material"),
        ("parameter_observations", "parameter"),
        ("geometry_observations", "geometry"),
        ("feed_port_excitation_observations", None),
    ):
        for record in response.pop(collection_name):
            record["evidence"] = [
                deepcopy(catalog[evidence_id])
                for evidence_id in record.pop("evidence_ids")
            ]
            record["kind"] = record.pop("observation_kind") if kind is None else kind
            observations.append(record)
    response["observations"] = observations

    for result in response["results"]:
        result["representation"] = _flatten_result_representation(
            result["representation"]
        )
    return response


def _flatten_result_representation(representation: dict) -> dict:
    kind = representation["kind"]
    if kind == "scalar":
        return {"kind": kind, "scalar_value": representation["value"]}
    if kind == "interval":
        return {
            "kind": kind,
            "interval_lower": representation["lower"],
            "interval_upper": representation["upper"],
        }
    if kind == "point_collection":
        return {"kind": kind, "collection_points": representation["points"]}
    if kind == "sampled_series":
        return {
            "kind": kind,
            "series_x_axis": representation["x_axis"],
            "series_y_axis": representation["y_axis"],
            "series_trace_label": representation["trace_label"],
            "series_points": representation["points"],
        }
    if kind == "matrix":
        return {
            "kind": kind,
            "matrix_rows": representation["rows"],
            "matrix_row_labels": representation["row_labels"],
            "matrix_column_labels": representation["column_labels"],
        }
    if kind == "angular_pattern":
        return {
            "kind": "sampled_angular_pattern",
            "angular_coordinate": representation["angular_coordinate"],
            "angular_unit": representation["angular_unit"],
            "angular_plane_or_cut": representation["plane_or_cut"],
            "angular_fixed_angle": representation["fixed_angle"],
            "angular_component_or_polarization": representation[
                "component_or_polarization"
            ],
            "angular_radial_quantity": representation["radial_quantity"],
            "angular_points": representation["points"],
        }
    if kind == "spatial_map":
        return _flatten_spatial_map_representation(representation)
    if kind == "image_only":
        return {
            "kind": kind,
            "image_axes": representation["axes"],
            "image_trace_labels": representation["trace_labels"],
            "image_annotated_points": representation["annotated_points"],
        }
    if kind == "qualitative":
        return {
            "kind": kind,
            "qualitative_observation": representation["observation"],
        }
    return {
        "kind": kind,
        "unavailable_reason": representation["reason"],
        "unavailable_description": representation["description"],
    }


def _flatten_spatial_map_representation(representation: dict) -> dict:
    content = representation["content"]
    flattened = {
        "kind": (
            "sampled_spatial_map"
            if content["kind"] == "sampled"
            else "image_spatial_map"
        ),
        "spatial_quantity": representation["quantity"],
    }
    if content["kind"] == "sampled":
        flattened.update(
            spatial_coordinate_description=content["coordinate_description"],
            spatial_samples=content["samples"],
        )
    else:
        flattened.update(
            spatial_map_type_or_component=content["map_type_or_component"],
            spatial_plane_or_cut=content["plane_or_cut"],
            spatial_legend_or_scale_label=content["legend_or_scale_label"],
            spatial_annotated_points=content["annotated_points"],
        )
    return flattened


def _settings() -> AntennaIngestSettings:
    return AntennaIngestSettings(
        skynet_base_url=(
            "https://endpoint-user:endpoint-password@example.invalid/openai"
            "?api_key=url-secret"
        ),
        skynet_api_key=SecretStr("api-secret"),
        document_extractor_model="test-extractor",
        architecture_author_model="test-author",
        document_extractor_timeout_seconds=240,
        document_extractor_max_output_tokens=12345,
        architecture_author_timeout_seconds=720,
        _env_file=None,
    )


def _failure_and_manifest(run_dir: Path) -> tuple[dict, RunManifest]:
    manifest = RunManifest.model_validate(read_json(run_dir / "manifest.json"))
    failure_reference = manifest.phases["paper_extraction"].failure_reference
    assert failure_reference is not None
    return read_json(run_dir / failure_reference), manifest
