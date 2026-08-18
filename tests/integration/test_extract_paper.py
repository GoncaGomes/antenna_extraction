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
from antenna_ingest.extraction.full_document import (
    EXTRACTION_PROMPT,
    EXTRACTION_REPORT_PATH,
    EXTRACTION_VALIDATION_PATH,
    PAPER_EXTRACTION_PATH,
    RAW_RESPONSE_PATH,
    REQUEST_METADATA_PATH,
    extract_paper_from_run,
)
from antenna_ingest.extraction.nuextract_contract import NuExtractPaperExtraction
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
    raw_response = json.dumps(_valid_extraction(run_dir), ensure_ascii=False)
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
    assert request["extra_body"] == {
        "chat_template_kwargs": {"enable_thinking": enable_thinking}
    }
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
    assert (
        sum(
            EXTRACTION_PROMPT in item.get("text", "")
            for item in content
            if item["type"] == "text"
        )
        == 1
    )
    prompt_text = content[0]["text"]
    for prompt_invariant in (
        "Do not extract paper-organisation statements",
        "Leave a collection empty when the paper contains no information",
        "Every emitted factual record must contain its supporting evidence inline",
        "The same source item may be repeated inline",
        "Do not include evidence merely because it concerns the same antenna",
        "Each inline evidence object must contain the correct page number",
        "Omit any claim that does not have direct source evidence",
        "the exact referenced design_id is declared by another record",
        "A reported width or span without explicit endpoints is a scalar",
        "Use interval only when the source explicitly reports both lower and upper endpoints",
    ):
        assert prompt_invariant in prompt_text
    assert "evidence_catalog" not in prompt_text
    assert "evidence_id" not in prompt_text

    manifest_before = RunManifest.model_validate(read_json(run_dir / "manifest.json"))
    assert manifest_before.document_id in prompt_text
    assert manifest_before.input_sha256 in prompt_text
    assert Path(manifest_before.input_file).name in prompt_text
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
    assert len(metadata["schema_hash"]) == 64
    assert (
        metadata["prompt_hash"]
        == hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()
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
    assert metadata_seen_before_call[0]["request_completed_at"] is None
    assert metadata_seen_before_call[0]["response_id"] is None
    assert metadata_seen_before_call[0]["temperature"] == expected_temperature

    assert (run_dir / RAW_RESPONSE_PATH).read_text(encoding="utf-8") == raw_response
    assert (run_dir / PAPER_EXTRACTION_PATH).is_file()
    assert (run_dir / EXTRACTION_REPORT_PATH).is_file()
    assert (run_dir / EXTRACTION_VALIDATION_PATH).is_file()
    manifest = RunManifest.model_validate(read_json(run_dir / "manifest.json"))
    assert manifest.phases["paper_extraction"].status == "completed"
    assert manifest.phases["paper_extraction"].attempt == 1
    assert manifest.phases["paper_extraction"].prompt_hash == metadata["prompt_hash"]
    assert manifest.phases["paper_extraction"].schema_hash == metadata["schema_hash"]
    PaperExtraction.model_validate(read_json(run_dir / PAPER_EXTRACTION_PATH))


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


def test_document_identity_contradiction_is_rejected_after_raw_persistence(
    tmp_path: Path,
) -> None:
    run_dir = _rendered_run(tmp_path)
    response_data = _valid_extraction(run_dir)
    response_data["document"]["document_id"] = "document_wrong"
    raw_response = json.dumps(response_data)
    client = FakeClient([raw_response])

    with pytest.raises(ValueError, match="contradicts manifest"):
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


def test_missing_optional_document_context_is_filled_from_manifest(
    tmp_path: Path,
) -> None:
    run_dir = _rendered_run(tmp_path)
    response_data = _valid_extraction(run_dir)
    response_data["document"]["source_filename"] = None
    response_data["document"]["sha256"] = None
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
    assert persisted_raw["document"]["source_filename"] is None
    assert persisted_raw["document"]["sha256"] is None
    assert validation_report["document_context_source"] == "manifest"
    assert validation_report["filled_document_fields"] == [
        "source_filename",
        "sha256",
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
    manifest = RunManifest.model_validate(read_json(run_dir / "manifest.json"))
    data["document"] = {
        "document_id": manifest.document_id,
        "page_count": 2,
        "source_filename": Path(manifest.input_file).name,
        "title": "Synthetic antenna paper",
        "doi": None,
        "sha256": manifest.input_sha256,
    }
    return _replace_evidence_ids_with_inline_evidence(data)


def _replace_evidence_ids_with_inline_evidence(data: dict) -> dict:
    response = deepcopy(data)
    catalog = {
        item["evidence_id"]: {
            key: value for key, value in item.items() if key != "evidence_id"
        }
        for item in response.pop("evidence_catalog")
    }

    collections = (
        "designs",
        "material_observations",
        "parameter_observations",
        "geometry_observations",
        "feed_port_excitation_observations",
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

    for result in response["results"]:
        representation = result["representation"]
        if representation["kind"] == "image_only":
            representation["evidence"] = [
                deepcopy(catalog[evidence_id])
                for evidence_id in representation.pop("evidence_ids")
            ]
        if (
            representation["kind"] == "spatial_map"
            and representation["content"]["kind"] == "image_only"
        ):
            content = representation["content"]
            content["evidence"] = [
                deepcopy(catalog[evidence_id])
                for evidence_id in content.pop("evidence_ids")
            ]
    return response


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
        architecture_author_timeout_seconds=720,
        _env_file=None,
    )


def _failure_and_manifest(run_dir: Path) -> tuple[dict, RunManifest]:
    manifest = RunManifest.model_validate(read_json(run_dir / "manifest.json"))
    failure_reference = manifest.phases["paper_extraction"].failure_reference
    assert failure_reference is not None
    return read_json(run_dir / failure_reference), manifest
