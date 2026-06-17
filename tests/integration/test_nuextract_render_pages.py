from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from antenna_ingest.nuextract.pdf_rendering import render_run_pages
from antenna_ingest.orchestration.runs import create_run
from antenna_ingest.orchestration.schemas import RunManifest
from antenna_ingest.utils.json_io import read_json


def test_render_run_pages_writes_pages_report_and_manifest(tmp_path) -> None:
    article_pdf = tmp_path / "article.pdf"
    make_test_pdf(article_pdf, page_count=2)
    context = create_run(article_pdf, runs_root=tmp_path / "runs")

    report = render_run_pages(context.run_dir, dpi=100)

    assert (context.run_dir / "parsed/pages/page_001.png").exists()
    assert (context.run_dir / "parsed/pages/page_002.png").exists()
    assert (context.run_dir / "parsed/page_render_report.json").exists()
    assert report.page_count == 2
    assert len(report.pages) == 2
    assert all(page.width_px > 0 and page.height_px > 0 for page in report.pages)

    manifest = RunManifest.model_validate(read_json(context.run_dir / "manifest.json"))
    assert manifest.phase_status["page_rendering"] == "completed"
    artifact_names = {artifact.name for artifact in manifest.artifacts}
    assert "source_pdf" in artifact_names
    assert "rendered_pages" in artifact_names
    assert "page_render_report" in artifact_names
    report_artifact = next(
        artifact
        for artifact in manifest.artifacts
        if artifact.name == "page_render_report"
    )
    assert report_artifact.checksum


def test_render_run_pages_refuses_existing_outputs_without_force(tmp_path) -> None:
    context = _create_test_run(tmp_path)
    render_run_pages(context.run_dir)

    with pytest.raises(FileExistsError):
        render_run_pages(context.run_dir)


def test_render_run_pages_allows_existing_outputs_with_force(tmp_path) -> None:
    context = _create_test_run(tmp_path)
    render_run_pages(context.run_dir)

    report = render_run_pages(context.run_dir, force=True)

    assert report.page_count == 2


def test_render_run_pages_marks_manifest_failed_on_error(tmp_path, monkeypatch) -> None:
    context = _create_test_run(tmp_path)

    def fail_open(_path):
        raise RuntimeError("render failed")

    monkeypatch.setattr(fitz, "open", fail_open)

    with pytest.raises(RuntimeError, match="render failed"):
        render_run_pages(context.run_dir)

    manifest = RunManifest.model_validate(read_json(context.run_dir / "manifest.json"))
    assert manifest.phase_status["page_rendering"] == "failed"


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
