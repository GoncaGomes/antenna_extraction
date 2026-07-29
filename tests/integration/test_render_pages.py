from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from antenna_ingest.orchestration.runs import create_run
from antenna_ingest.orchestration.schemas import RunManifest
from antenna_ingest.rendering import render_run_pages
from antenna_ingest.utils.json_io import read_json


def test_render_run_pages_writes_ordered_pages_report_and_manifest(tmp_path) -> None:
    article_pdf = tmp_path / "article.pdf"
    make_test_pdf(article_pdf, page_count=2)
    context = create_run(article_pdf, runs_root=tmp_path / "runs")

    report = render_run_pages(context.run_dir, dpi=100)

    expected_paths = [
        "pages/page_0001.png",
        "pages/page_0002.png",
    ]
    assert [page.page_number for page in report.pages] == [1, 2]
    assert [page.relative_path for page in report.pages] == expected_paths
    assert all((context.run_dir / path).is_file() for path in expected_paths)
    assert (context.run_dir / "pages/render_report.json").is_file()
    assert all(page.width_px > 0 and page.height_px > 0 for page in report.pages)

    manifest = RunManifest.model_validate(read_json(context.run_dir / "manifest.json"))
    assert manifest.phases["page_rendering"].status == "completed"
    assert manifest.phases["page_rendering"].input_artifact_names == ["source_pdf"]
    assert manifest.phases["page_rendering"].output_artifact_names == [
        "rendered_pages",
        "render_report",
    ]
    artifacts = {artifact.name: artifact for artifact in manifest.artifacts}
    assert set(artifacts) == {"source_pdf", "rendered_pages", "render_report"}
    assert artifacts["render_report"].checksum


def test_render_run_pages_refuses_existing_outputs_without_force(tmp_path) -> None:
    context = _create_test_run(tmp_path)
    render_run_pages(context.run_dir)

    with pytest.raises(FileExistsError):
        render_run_pages(context.run_dir)


def test_render_run_pages_replaces_outputs_with_force(tmp_path) -> None:
    context = _create_test_run(tmp_path)
    render_run_pages(context.run_dir)

    report = render_run_pages(context.run_dir, force=True)
    manifest = RunManifest.model_validate(read_json(context.run_dir / "manifest.json"))

    assert report.page_count == 2
    assert manifest.phases["page_rendering"].attempt == 2
    assert [artifact.name for artifact in manifest.artifacts].count(
        "render_report"
    ) == 1


def test_render_run_pages_marks_manifest_failed_on_error(tmp_path, monkeypatch) -> None:
    context = _create_test_run(tmp_path)

    def fail_open(_path):
        raise RuntimeError("render failed")

    monkeypatch.setattr(fitz, "open", fail_open)

    with pytest.raises(RuntimeError, match="render failed"):
        render_run_pages(context.run_dir)

    manifest = RunManifest.model_validate(read_json(context.run_dir / "manifest.json"))
    assert manifest.phases["page_rendering"].status == "failed"


def make_test_pdf(path: Path, page_count: int = 2) -> None:
    document = fitz.open()
    try:
        for index in range(page_count):
            page = document.new_page()
            page.insert_text((72, 72), f"Test page {index + 1}")
        document.save(path)
    finally:
        document.close()


def _create_test_run(tmp_path):
    article_pdf = tmp_path / "article.pdf"
    make_test_pdf(article_pdf, page_count=2)
    return create_run(article_pdf, runs_root=tmp_path / "runs")
