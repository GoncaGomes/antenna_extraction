from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import SecretStr, ValidationError

from antenna_ingest.nuextract.markdown_conversion import (
    DOCUMENT_MARKDOWN_PATH,
    MARKDOWN_CONVERSION_PROMPT,
    MARKDOWN_REPORT_PATH,
    MarkdownPageResult,
    NuExtractMarkdownReport,
    clean_markdown_output,
    combine_page_markdown,
    convert_run_pages_to_markdown,
    image_file_to_data_url,
    refuse_existing_markdown_outputs,
    request_page_markdown,
)
from antenna_ingest.nuextract.pdf_rendering import PageRenderReport, RenderedPage
from antenna_ingest.nuextract.settings import NuExtractSettings
from antenna_ingest.orchestration.schemas import RunManifest
from antenna_ingest.utils.json_io import write_json


def test_nuextract_markdown_report_validates_minimal_report() -> None:
    report = NuExtractMarkdownReport(
        converter_name="nuextract3_markdown",
        model="nuextract3",
        source_pages_dir="parsed/pages",
        source_page_render_report="parsed/page_render_report.json",
        output_markdown="parsed/document.nuextract.md",
        page_count=1,
        character_count=10,
        pages=[
            MarkdownPageResult(
                page_number=1,
                image_path="parsed/pages/page_001.png",
                markdown_character_count=10,
            )
        ],
    )

    assert report.page_count == 1


def test_markdown_page_result_rejects_page_number_zero() -> None:
    with pytest.raises(ValidationError):
        MarkdownPageResult(
            page_number=0,
            image_path="parsed/pages/page_001.png",
            markdown_character_count=10,
        )


def test_image_file_to_data_url_returns_png_data_url(tmp_path) -> None:
    image_path = tmp_path / "page.png"
    image_path.write_bytes(b"image bytes")

    data_url = image_file_to_data_url(image_path)

    assert data_url.startswith("data:image/png;base64,")


def test_combine_page_markdown_adds_page_markers_and_final_newline() -> None:
    markdown = combine_page_markdown([(1, "# Page 1"), (2, "# Page 2")])

    assert "<!-- page: 1 -->" in markdown
    assert "# Page 1" in markdown
    assert "<!-- page: 2 -->" in markdown
    assert "# Page 2" in markdown
    assert markdown.endswith("\n")


def test_clean_markdown_output_removes_long_repeated_html_nbsp() -> None:
    markdown = clean_markdown_output("A&nbsp; &nbsp;&nbsp;&nbsp;&nbsp;B")

    assert markdown == "A B\n"


def test_clean_markdown_output_removes_long_repeated_unicode_nbsp() -> None:
    markdown = clean_markdown_output("A\u00a0\u00a0\u00a0\u00a0\u00a0B")

    assert markdown == "A B\n"


def test_clean_markdown_output_keeps_useful_markdown_content_intact() -> None:
    markdown = clean_markdown_output("# Title\n\n- gain: 5 dBi\n- frequency: 2.4 GHz")

    assert markdown == "# Title\n\n- gain: 5 dBi\n- frequency: 2.4 GHz\n"


def test_refuse_existing_markdown_outputs_raises_when_markdown_exists(tmp_path) -> None:
    run_dir = tmp_path / "run"
    markdown_path = run_dir / DOCUMENT_MARKDOWN_PATH
    markdown_path.parent.mkdir(parents=True)
    markdown_path.write_text("# Existing", encoding="utf-8")

    with pytest.raises(FileExistsError):
        refuse_existing_markdown_outputs(run_dir, force=False)


def test_refuse_existing_markdown_outputs_removes_outputs_with_force(tmp_path) -> None:
    run_dir = tmp_path / "run"
    markdown_path = run_dir / DOCUMENT_MARKDOWN_PATH
    report_path = run_dir / MARKDOWN_REPORT_PATH
    markdown_path.parent.mkdir(parents=True)
    markdown_path.write_text("# Existing", encoding="utf-8")
    report_path.write_text("{}", encoding="utf-8")

    refuse_existing_markdown_outputs(run_dir, force=True)

    assert not markdown_path.exists()
    assert not report_path.exists()


def test_request_page_markdown_sends_expected_payload() -> None:
    fake_client = FakeClient(["# Page 1"])

    result = request_page_markdown(
        client=fake_client,
        model="nuextract3",
        image_data_url="data:image/png;base64,abc",
    )

    request = fake_client.requests[0]
    message = request["messages"][0]
    assert request["model"] == "nuextract3"
    assert message["content"][0] == {
        "type": "text",
        "text": MARKDOWN_CONVERSION_PROMPT,
    }
    assert message["content"][1] == {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,abc"},
    }
    assert request["temperature"] == 0
    assert request["max_tokens"] == 4096
    assert result == "# Page 1"


def test_fake_settings_can_be_injected() -> None:
    settings = NuExtractSettings(
        OPENAI_BASE_URL="https://example.invalid/openai",
        OLLAMA_MODEL="nuextract3",
        SKYNET_API_KEY=SecretStr("secret"),
    )

    assert settings.ollama_model == "nuextract3"


def test_convert_run_pages_to_markdown_stores_cleaned_markdown(tmp_path) -> None:
    run_dir = tmp_path / "run"
    page_path = run_dir / "parsed/pages/page_001.png"
    page_path.parent.mkdir(parents=True)
    page_path.write_bytes(b"fake png")
    write_json(
        run_dir / "manifest.json",
        RunManifest(
            run_id="run_1",
            input_file="input/article.pdf",
            pipeline_version="0.1.0",
            phase_status={"nuextract_markdown": "pending"},
        ).model_dump(mode="json"),
    )
    write_json(
        run_dir / "parsed/page_render_report.json",
        PageRenderReport(
            renderer_name="pymupdf",
            source_document="input/article.pdf",
            dpi=170,
            page_count=1,
            pages=[
                RenderedPage(
                    page_number=1,
                    relative_path="parsed/pages/page_001.png",
                    width_px=100,
                    height_px=100,
                )
            ],
        ).model_dump(mode="json"),
    )

    report = convert_run_pages_to_markdown(
        run_dir,
        settings=_settings(),
        client=FakeClient(["# Page&nbsp; &nbsp;&nbsp;&nbsp;&nbsp;1"]),
    )

    markdown = (run_dir / DOCUMENT_MARKDOWN_PATH).read_text(encoding="utf-8")
    assert "&nbsp;" not in markdown
    assert "# Page 1" in markdown
    assert report.pages[0].markdown_character_count == len("# Page 1\n")


def _settings() -> NuExtractSettings:
    return NuExtractSettings(
        OPENAI_BASE_URL="https://example.invalid/openai",
        OLLAMA_MODEL="nuextract3",
        SKYNET_API_KEY=SecretStr("secret"),
    )


class FakeClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.requests: list[dict] = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create),
        )

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        content = self.responses.pop(0)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=content),
                )
            ]
        )
