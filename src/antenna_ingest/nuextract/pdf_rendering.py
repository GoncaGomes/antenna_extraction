from __future__ import annotations

import shutil
from pathlib import Path

import fitz
from pydantic import Field

from antenna_ingest.orchestration.phases import complete_phase, fail_phase, start_phase
from antenna_ingest.orchestration.runs import load_run_manifest, sha256_file
from antenna_ingest.orchestration.schemas import (
    ArtifactReference,
    RunManifest,
    StrictModel,
)
from antenna_ingest.utils.json_io import write_json


RENDERER_NAME = "pymupdf"
PAGES_DIR = "parsed/pages"
PAGE_RENDER_REPORT_PATH = "parsed/page_render_report.json"
PAGE_RENDERING_PHASE = "page_rendering"


class RenderedPage(StrictModel):
    page_number: int = Field(ge=1)
    relative_path: str = Field(min_length=1)
    width_px: int = Field(ge=1)
    height_px: int = Field(ge=1)


class PageRenderReport(StrictModel):
    renderer_name: str = Field(min_length=1)
    source_document: str = Field(min_length=1)
    dpi: int = Field(ge=1)
    page_count: int = Field(ge=1)
    pages: list[RenderedPage] = Field(min_length=1)
    warnings: list[str] = Field(default_factory=list)


def render_run_pages(
    run_dir: Path,
    dpi: int = 170,
    force: bool = False,
) -> PageRenderReport:
    run_dir = Path(run_dir).resolve()
    manifest_path = run_dir / "manifest.json"
    manifest = load_run_manifest(manifest_path)
    input_pdf = find_input_pdf(run_dir, manifest)
    source_document = input_pdf.relative_to(run_dir).as_posix()

    refuse_existing_render_outputs(run_dir, force)
    pages_dir = run_dir / PAGES_DIR
    pages_dir.mkdir(parents=True, exist_ok=True)

    start_phase(manifest, PAGE_RENDERING_PHASE)
    write_json(manifest_path, manifest.model_dump(mode="json"))

    try:
        pages = _render_pdf_pages(input_pdf, run_dir, dpi)
        report = PageRenderReport(
            renderer_name=RENDERER_NAME,
            source_document=source_document,
            dpi=dpi,
            page_count=len(pages),
            pages=pages,
            warnings=[],
        )
        write_json(run_dir / PAGE_RENDER_REPORT_PATH, report.model_dump(mode="json"))

        manifest = load_run_manifest(manifest_path)
        complete_phase(manifest, PAGE_RENDERING_PHASE)
        replace_page_rendering_artifacts(manifest, run_dir)
        write_json(manifest_path, manifest.model_dump(mode="json"))
        return report
    except Exception:
        failed_manifest = load_run_manifest(manifest_path)
        fail_phase(failed_manifest, PAGE_RENDERING_PHASE, None)
        write_json(manifest_path, failed_manifest.model_dump(mode="json"))
        raise


def find_input_pdf(run_dir: Path, manifest: RunManifest) -> Path:
    pdf_path = Path(run_dir) / manifest.input_file
    if pdf_path.exists() and pdf_path.is_file():
        return pdf_path

    input_dir = Path(run_dir) / "input"
    pdfs = sorted(input_dir.glob("*.pdf"))
    if len(pdfs) == 1:
        return pdfs[0]
    if not pdfs:
        raise FileNotFoundError(f"no input PDF found in {input_dir}")
    raise ValueError(f"multiple input PDFs found in {input_dir}")


def refuse_existing_render_outputs(run_dir: Path, force: bool) -> None:
    pages_dir = Path(run_dir) / PAGES_DIR
    report_path = Path(run_dir) / PAGE_RENDER_REPORT_PATH
    if not force:
        if pages_dir.exists():
            raise FileExistsError(f"rendered pages already exist: {pages_dir}")
        if report_path.exists():
            raise FileExistsError(f"page render report already exists: {report_path}")
        return

    if pages_dir.exists():
        shutil.rmtree(pages_dir)
    if report_path.exists():
        report_path.unlink()


def replace_page_rendering_artifacts(
    manifest: RunManifest,
    run_dir: Path,
) -> None:
    artifact_names = {"rendered_pages", "page_render_report"}
    manifest.artifacts = [
        artifact
        for artifact in manifest.artifacts
        if artifact.name not in artifact_names
    ]
    manifest.add_artifact(
        ArtifactReference(
            name="rendered_pages",
            relative_path=PAGES_DIR,
            producing_phase=PAGE_RENDERING_PHASE,
            checksum=None,
        )
    )
    manifest.add_artifact(
        ArtifactReference(
            name="page_render_report",
            relative_path=PAGE_RENDER_REPORT_PATH,
            producing_phase=PAGE_RENDERING_PHASE,
            checksum=sha256_file(Path(run_dir) / PAGE_RENDER_REPORT_PATH),
        )
    )


def _render_pdf_pages(input_pdf: Path, run_dir: Path, dpi: int) -> list[RenderedPage]:
    document = fitz.open(input_pdf)
    try:
        zoom = dpi / 72
        matrix = fitz.Matrix(zoom, zoom)
        rendered_pages: list[RenderedPage] = []
        for index in range(document.page_count):
            page = document.load_page(index)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            relative_path = f"{PAGES_DIR}/page_{index + 1:03d}.png"
            output_path = Path(run_dir) / relative_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            pixmap.save(output_path)
            rendered_pages.append(
                RenderedPage(
                    page_number=index + 1,
                    relative_path=relative_path,
                    width_px=pixmap.width,
                    height_px=pixmap.height,
                )
            )
        return rendered_pages
    finally:
        document.close()
