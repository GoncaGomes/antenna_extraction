from __future__ import annotations

import pytest
from pydantic import ValidationError

from antenna_ingest.orchestration.schemas import (
    RUN_PHASES,
    PhaseExecution,
    PhaseStatus,
    RunFingerprint,
    RunManifest,
)
from antenna_ingest.rendering import (
    PAGES_DIR,
    PAGE_RENDER_REPORT_PATH,
    PageRenderReport,
    RenderedPage,
    find_input_pdf,
    refuse_existing_render_outputs,
)


def test_page_render_report_validates_ordered_page_metadata() -> None:
    report = PageRenderReport(
        renderer_name="pymupdf",
        source_document="input/article.pdf",
        dpi=170,
        page_count=1,
        pages=[
            RenderedPage(
                page_number=1,
                relative_path="pages/page_0001.png",
                width_px=100,
                height_px=100,
            )
        ],
    )

    assert report.pages[0].relative_path == "pages/page_0001.png"


def test_rendered_page_and_report_reject_non_positive_values() -> None:
    with pytest.raises(ValidationError):
        RenderedPage(
            page_number=0,
            relative_path="pages/page_0001.png",
            width_px=100,
            height_px=100,
        )
    with pytest.raises(ValidationError):
        PageRenderReport(
            renderer_name="pymupdf",
            source_document="input/article.pdf",
            dpi=0,
            page_count=1,
            pages=[
                RenderedPage(
                    page_number=1,
                    relative_path="pages/page_0001.png",
                    width_px=100,
                    height_px=100,
                )
            ],
        )


def test_find_input_pdf_uses_manifest_then_single_pdf_fallback(tmp_path) -> None:
    run_dir = tmp_path / "run"
    input_dir = run_dir / "input"
    input_dir.mkdir(parents=True)
    pdf_path = input_dir / "article.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    manifest = _manifest("input/article.pdf")

    assert find_input_pdf(run_dir, manifest) == pdf_path

    manifest.input_file = "input/missing.pdf"
    assert find_input_pdf(run_dir, manifest) == pdf_path


def test_refuse_existing_render_outputs_requires_force(tmp_path) -> None:
    run_dir = tmp_path / "run"
    pages_dir = run_dir / PAGES_DIR
    pages_dir.mkdir(parents=True)
    (pages_dir / "page_0001.png").write_bytes(b"page")
    (run_dir / PAGE_RENDER_REPORT_PATH).write_text("{}", encoding="utf-8")

    with pytest.raises(FileExistsError):
        refuse_existing_render_outputs(run_dir, force=False)

    refuse_existing_render_outputs(run_dir, force=True)
    assert not pages_dir.exists()


def _manifest(input_file: str) -> RunManifest:
    return RunManifest(
        run_id="run_1",
        input_file=input_file,
        document_id="document_123456789abc",
        input_sha256="a" * 64,
        pipeline_version="0.1.0",
        fingerprint=RunFingerprint(
            python_version="3.12.0",
            platform="test-platform",
        ),
        phases={
            name: PhaseExecution(
                status=(
                    PhaseStatus.COMPLETED
                    if name == "run_initialization"
                    else PhaseStatus.PENDING
                )
            )
            for name in RUN_PHASES
        },
    )
