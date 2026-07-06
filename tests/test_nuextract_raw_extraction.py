from __future__ import annotations

import base64
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from antenna_ingest.nuextract.candidate_template import (
    ANTENNA_DESIGN_CANDIDATE_INSTRUCTIONS,
    ANTENNA_DESIGN_CANDIDATE_TEMPLATE,
)
from antenna_ingest.nuextract.pdf_rendering import PageRenderReport, RenderedPage
from antenna_ingest.nuextract.raw_extraction import (
    ANTENNA_CANDIDATE_PATH,
    CLEANED_RESPONSE_TRACE_PATH,
    EXTRACTION_REPORT_PATH,
    PARSE_ERROR_TRACE_PATH,
    RAW_RESPONSE_TRACE_PATH,
    REQUEST_METADATA_PATH,
    clean_nuextract_json_response,
    extract_antenna_candidate_from_run,
    parse_candidate_response,
)
from antenna_ingest.nuextract.settings import NuExtractSettings
from antenna_ingest.orchestration.schemas import RunManifest
from antenna_ingest.utils.json_io import read_json, write_json


def test_extraction_sends_all_pages_once_and_writes_outputs(tmp_path) -> None:
    run_dir = _make_rendered_run(tmp_path)
    client = FakeClient(_candidate_json())

    candidate, report = extract_antenna_candidate_from_run(
        run_dir,
        settings=_settings(),
        client=client,
    )

    assert candidate.schema_name == "antenna_design_candidate_v2"
    assert report.page_count == 2
    assert report.thinking_enabled is True
    assert report.temperature == 0.0
    assert (run_dir / ANTENNA_CANDIDATE_PATH).exists()
    assert (run_dir / EXTRACTION_REPORT_PATH).exists()
    assert (run_dir / REQUEST_METADATA_PATH).exists()
    assert len(client.requests) == 1

    request = client.requests[0]
    content = request["messages"][0]["content"]
    assert content == [
        {"type": "text", "text": "PDF_INPUT_PAGE=1"},
        {
            "type": "image_url",
            "image_url": {"url": _data_url(b"first page")},
        },
        {"type": "text", "text": "PDF_INPUT_PAGE=2"},
        {
            "type": "image_url",
            "image_url": {"url": _data_url(b"second page")},
        },
    ]
    chat_template = request["extra_body"]["chat_template_kwargs"]
    assert chat_template["template"] == json.dumps(
        ANTENNA_DESIGN_CANDIDATE_TEMPLATE,
        indent=2,
    )
    assert chat_template["instructions"] == ANTENNA_DESIGN_CANDIDATE_INSTRUCTIONS
    assert chat_template["enable_thinking"] is True
    assert request["temperature"] == 0.0

    metadata = read_json(run_dir / REQUEST_METADATA_PATH)
    assert metadata == {
        "model": "nuextract3",
        "temperature": 0.0,
        "max_tokens": None,
        "enable_thinking": True,
        "page_count": 2,
        "template_version": "antenna_design_candidate_v2",
        "timeout_seconds": 180,
    }

    manifest = RunManifest.model_validate(read_json(run_dir / "manifest.json"))
    assert manifest.phase_status["nuextract_raw_extraction"] == "completed"
    artifact_names = {artifact.name for artifact in manifest.artifacts}
    assert "nuextract3_antenna_candidate" in artifact_names
    assert "nuextract3_extraction_report" in artifact_names
    assert "nuextract3_request_metadata" in artifact_names


def test_explicit_temperature_override_is_used(tmp_path) -> None:
    run_dir = _make_rendered_run(tmp_path)
    client = FakeClient(_candidate_json())

    _candidate, report = extract_antenna_candidate_from_run(
        run_dir,
        settings=_settings(),
        client=client,
        temperature=0.2,
    )

    assert client.requests[0]["temperature"] == 0.2
    assert report.temperature == 0.2
    assert read_json(run_dir / REQUEST_METADATA_PATH)["temperature"] == 0.2


def test_thinking_and_json_fences_are_removed_before_parsing() -> None:
    content = f"<think>private reasoning</think>```json\n{_candidate_json()}\n```"

    cleaned = clean_nuextract_json_response(content)
    candidate = parse_candidate_response(content)

    assert "private reasoning" not in cleaned
    assert cleaned.startswith("{")
    assert candidate.schema_name == "antenna_design_candidate_v2"


def test_invalid_source_page_adds_report_warning(tmp_path) -> None:
    run_dir = _make_rendered_run(tmp_path)
    client = FakeClient(_candidate_json(summary_evidence_page=1207))

    _candidate, report = extract_antenna_candidate_from_run(
        run_dir,
        settings=_settings(),
        client=client,
    )

    assert report.warnings
    assert "1207" in report.warnings[0]
    assert "1..2" in report.warnings[0]
    stored_report = read_json(run_dir / EXTRACTION_REPORT_PATH)
    assert stored_report["warnings"] == report.warnings


def test_existing_outputs_are_refused_without_force(tmp_path) -> None:
    run_dir = _make_rendered_run(tmp_path)
    extract_antenna_candidate_from_run(
        run_dir,
        settings=_settings(),
        client=FakeClient(_candidate_json()),
    )

    with pytest.raises(FileExistsError):
        extract_antenna_candidate_from_run(
            run_dir,
            settings=_settings(),
            client=FakeClient(_candidate_json()),
        )


def test_existing_outputs_are_replaced_with_force(tmp_path) -> None:
    run_dir = _make_rendered_run(tmp_path)
    extract_antenna_candidate_from_run(
        run_dir,
        settings=_settings(),
        client=FakeClient(_candidate_json(title="First")),
    )

    candidate, _report = extract_antenna_candidate_from_run(
        run_dir,
        force=True,
        settings=_settings(),
        client=FakeClient(_candidate_json(title="Second")),
    )

    assert candidate.document.title == "Second"


def test_client_error_marks_extraction_failed(tmp_path) -> None:
    run_dir = _make_rendered_run(tmp_path)

    with pytest.raises(RuntimeError, match="extraction failed"):
        extract_antenna_candidate_from_run(
            run_dir,
            settings=_settings(),
            client=FailingClient(),
        )

    manifest = RunManifest.model_validate(read_json(run_dir / "manifest.json"))
    assert manifest.phase_status["nuextract_raw_extraction"] == "failed"


def test_invalid_json_response_writes_parse_traces(tmp_path) -> None:
    run_dir = _make_rendered_run(tmp_path)
    response = "<think>ignored</think>```json\n{\"schema_name\": bad}\n```"

    with pytest.raises(json.JSONDecodeError):
        extract_antenna_candidate_from_run(
            run_dir,
            settings=_settings(),
            client=FakeClient(response),
        )

    assert (run_dir / RAW_RESPONSE_TRACE_PATH).read_text(
        encoding="utf-8"
    ) == response
    assert (run_dir / CLEANED_RESPONSE_TRACE_PATH).read_text(
        encoding="utf-8"
    ) == '{"schema_name": bad}'
    parse_error = (run_dir / PARSE_ERROR_TRACE_PATH).read_text(encoding="utf-8")
    assert "JSONDecodeError" in parse_error
    assert "char_position" in parse_error
    assert "context:" in parse_error
    manifest = RunManifest.model_validate(read_json(run_dir / "manifest.json"))
    assert manifest.phase_status["nuextract_raw_extraction"] == "failed"


def _make_rendered_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run"
    pages = [
        RenderedPage(
            page_number=1,
            relative_path="parsed/pages/page_001.png",
            width_px=100,
            height_px=100,
        ),
        RenderedPage(
            page_number=2,
            relative_path="parsed/pages/page_002.png",
            width_px=100,
            height_px=100,
        ),
    ]
    for page, content in zip(pages, [b"first page", b"second page"], strict=True):
        image_path = run_dir / page.relative_path
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(content)

    write_json(
        run_dir / "manifest.json",
        RunManifest(
            run_id="run_1",
            input_file="input/article.pdf",
            pipeline_version="0.1.0",
            phase_status={"nuextract_raw_extraction": "pending"},
        ).model_dump(mode="json"),
    )
    write_json(
        run_dir / "parsed/page_render_report.json",
        PageRenderReport(
            renderer_name="pymupdf",
            source_document="input/article.pdf",
            dpi=170,
            page_count=2,
            pages=pages,
        ).model_dump(mode="json"),
    )
    return run_dir


def _candidate_json(
    title: str = "Test antenna",
    summary_evidence_page: int | None = None,
) -> str:
    evidence = []
    if summary_evidence_page is not None:
        evidence.append(
            {
                "page": summary_evidence_page,
                "quote": "reported on journal page 1207",
                "confidence": 0.8,
            }
        )

    return json.dumps(
        {
            "schema_name": "antenna_design_candidate_v2",
            "document": {"title": title},
            "summary": {
                "evidence": evidence,
            },
        }
    )


def _settings() -> NuExtractSettings:
    return NuExtractSettings(
        SKYNET_BASE_URL="https://example.invalid/openai",
        NUEXTRACT_MODEL="nuextract3",
        SKYNET_API_KEY=SecretStr("secret"),
    )


def _data_url(content: bytes) -> str:
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:image/png;base64,{encoded}"


class FakeClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.requests: list[dict] = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create),
        )

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self.response),
                )
            ]
        )


class FailingClient:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create),
        )

    def _create(self, **_kwargs):
        raise RuntimeError("extraction failed")
