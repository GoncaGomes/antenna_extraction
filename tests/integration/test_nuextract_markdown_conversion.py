from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import fitz
import pytest
from pydantic import SecretStr

from antenna_ingest.nuextract.markdown_conversion import (
    MARKDOWN_REPORT_PATH,
    convert_run_pages_to_markdown,
    parse_pdf_to_markdown,
)
from antenna_ingest.nuextract.pdf_rendering import render_run_pages
from antenna_ingest.nuextract.settings import NuExtractSettings
from antenna_ingest.orchestration.runs import create_run
from antenna_ingest.orchestration.schemas import RunManifest
from antenna_ingest.utils.json_io import read_json


def test_convert_run_pages_to_markdown_writes_outputs_and_manifest(tmp_path) -> None:
    article_pdf = tmp_path / "article.pdf"
    make_test_pdf(article_pdf, page_count=2)
    context = create_run(article_pdf, runs_root=tmp_path / "runs")
    render_run_pages(context.run_dir)

    report = convert_run_pages_to_markdown(
        context.run_dir,
        settings=_settings(),
        client=FakeMarkdownClient(["# Page 1", "# Page 2"]),
    )

    markdown_path = context.run_dir / "parsed/document.nuextract.md"
    report_path = context.run_dir / MARKDOWN_REPORT_PATH
    assert markdown_path.exists()
    assert report_path.exists()
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "<!-- page: 1 -->" in markdown
    assert "# Page 1" in markdown
    assert "<!-- page: 2 -->" in markdown
    assert "# Page 2" in markdown
    assert report.page_count == 2
    assert report.character_count > 0
    assert len(report.pages) == 2

    manifest = RunManifest.model_validate(read_json(context.run_dir / "manifest.json"))
    assert manifest.phases["nuextract_markdown"].status == "completed"
    artifact_names = {artifact.name for artifact in manifest.artifacts}
    assert "source_pdf" in artifact_names
    assert "rendered_pages" in artifact_names
    assert "page_render_report" in artifact_names
    assert "nuextract_markdown" in artifact_names
    assert "nuextract_markdown_report" in artifact_names


def test_convert_run_pages_to_markdown_refuses_existing_outputs(tmp_path) -> None:
    context = _create_rendered_run(tmp_path)
    convert_run_pages_to_markdown(
        context.run_dir,
        settings=_settings(),
        client=FakeMarkdownClient(["# Page 1", "# Page 2"]),
    )

    with pytest.raises(FileExistsError):
        convert_run_pages_to_markdown(
            context.run_dir,
            settings=_settings(),
            client=FakeMarkdownClient(["# Page 1", "# Page 2"]),
        )


def test_convert_run_pages_to_markdown_allows_existing_outputs_with_force(tmp_path) -> None:
    context = _create_rendered_run(tmp_path)
    convert_run_pages_to_markdown(
        context.run_dir,
        settings=_settings(),
        client=FakeMarkdownClient(["# Page 1", "# Page 2"]),
    )

    report = convert_run_pages_to_markdown(
        context.run_dir,
        force=True,
        settings=_settings(),
        client=FakeMarkdownClient(["# New Page 1", "# New Page 2"]),
    )

    assert report.page_count == 2


def test_convert_run_pages_to_markdown_marks_manifest_failed_on_error(tmp_path) -> None:
    context = _create_rendered_run(tmp_path)

    with pytest.raises(RuntimeError, match="markdown failed"):
        convert_run_pages_to_markdown(
            context.run_dir,
            settings=_settings(),
            client=FailingMarkdownClient(),
        )

    manifest = RunManifest.model_validate(read_json(context.run_dir / "manifest.json"))
    assert manifest.phases["nuextract_markdown"].status == "failed"


def test_parse_pdf_to_markdown_creates_run_renders_and_writes_markdown(tmp_path) -> None:
    article_pdf = tmp_path / "article.pdf"
    make_test_pdf(article_pdf, page_count=2)

    context, report = parse_pdf_to_markdown(
        article_pdf,
        runs_root=tmp_path / "runs",
        settings=_settings(),
        client=FakeMarkdownClient(["# Page 1", "# Page 2"]),
    )

    assert context.run_dir.exists()
    assert (context.run_dir / "parsed/pages/page_001.png").exists()
    assert (context.run_dir / "parsed/document.nuextract.md").exists()
    assert report.page_count == 2


def make_test_pdf(path: Path, page_count: int = 2) -> None:
    document = fitz.open()
    try:
        for index in range(page_count):
            page = document.new_page()
            page.insert_text((72, 72), f"Test page {index + 1}")
        document.save(path)
    finally:
        document.close()


def _create_rendered_run(tmp_path):
    article_pdf = tmp_path / "article.pdf"
    make_test_pdf(article_pdf, page_count=2)
    context = create_run(article_pdf, runs_root=tmp_path / "runs")
    render_run_pages(context.run_dir)
    return context


def _settings() -> NuExtractSettings:
    return NuExtractSettings(
        SKYNET_BASE_URL="https://example.invalid/openai",
        NUEXTRACT_MODEL="nuextract3",
        CANONICALIZER_MODEL="canonicalizer",
        SKYNET_API_KEY=SecretStr("secret"),
    )


class FakeMarkdownClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create),
        )

    def _create(self, **_kwargs):
        content = self.responses.pop(0)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=content),
                )
            ]
        )


class FailingMarkdownClient:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create),
        )

    def _create(self, **_kwargs):
        raise RuntimeError("markdown failed")
