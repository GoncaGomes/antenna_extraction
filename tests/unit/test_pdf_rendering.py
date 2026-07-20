from __future__ import annotations

import pytest
from pydantic import ValidationError

from antenna_ingest.nuextract.pdf_rendering import (
    PAGES_DIR,
    PAGE_RENDER_REPORT_PATH,
    PageRenderReport,
    RenderedPage,
    find_input_pdf,
    refuse_existing_render_outputs,
)
from antenna_ingest.orchestration.schemas import RunManifest


def test_page_render_report_validates_minimal_report() -> None:
    report = PageRenderReport(
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
    )

    assert report.page_count == 1


def test_rendered_page_rejects_page_number_zero() -> None:
    with pytest.raises(ValidationError):
        RenderedPage(
            page_number=0,
            relative_path="parsed/pages/page_001.png",
            width_px=100,
            height_px=100,
        )


def test_page_render_report_rejects_dpi_zero() -> None:
    with pytest.raises(ValidationError):
        PageRenderReport(
            renderer_name="pymupdf",
            source_document="input/article.pdf",
            dpi=0,
            page_count=1,
            pages=[
                RenderedPage(
                    page_number=1,
                    relative_path="parsed/pages/page_001.png",
                    width_px=100,
                    height_px=100,
                )
            ],
        )


def test_find_input_pdf_uses_manifest_input_file(tmp_path) -> None:
    run_dir = tmp_path / "run"
    pdf_path = run_dir / "input" / "article.pdf"
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_bytes(b"%PDF-1.4\n")
    manifest = _manifest(input_file="input/article.pdf")

    assert find_input_pdf(run_dir, manifest) == pdf_path


def test_find_input_pdf_falls_back_to_single_input_pdf(tmp_path) -> None:
    run_dir = tmp_path / "run"
    pdf_path = run_dir / "input" / "fallback.pdf"
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_bytes(b"%PDF-1.4\n")
    manifest = _manifest(input_file="input/missing.pdf")

    assert find_input_pdf(run_dir, manifest) == pdf_path


def test_refuse_existing_render_outputs_raises_for_existing_pages(tmp_path) -> None:
    run_dir = tmp_path / "run"
    (run_dir / PAGES_DIR).mkdir(parents=True)

    with pytest.raises(FileExistsError):
        refuse_existing_render_outputs(run_dir, force=False)


def test_refuse_existing_render_outputs_allows_force(tmp_path) -> None:
    run_dir = tmp_path / "run"
    pages_dir = run_dir / PAGES_DIR
    report_path = run_dir / PAGE_RENDER_REPORT_PATH
    pages_dir.mkdir(parents=True)
    report_path.write_text("{}", encoding="utf-8")

    refuse_existing_render_outputs(run_dir, force=True)

    assert not pages_dir.exists()
    assert not report_path.exists()


def _manifest(input_file: str) -> RunManifest:
    return RunManifest(
        run_id="run_1",
        input_file=input_file,
        pipeline_version="0.1.0",
        phases={"run_infrastructure": "completed"},
    )
