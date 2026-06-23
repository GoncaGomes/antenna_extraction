from __future__ import annotations

import re
from pathlib import Path

from pydantic import Field

from antenna_ingest.nuextract.client import build_nuextract_client
from antenna_ingest.nuextract.images import image_file_to_data_url
from antenna_ingest.nuextract.pdf_rendering import (
    PAGE_RENDER_REPORT_PATH,
    PAGES_DIR,
    PageRenderReport,
    render_run_pages,
)
from antenna_ingest.nuextract.settings import (
    NuExtractSettings,
    load_nuextract_settings,
)
from antenna_ingest.orchestration.runs import create_run, sha256_file
from antenna_ingest.orchestration.schemas import (
    ArtifactReference,
    PhaseStatus,
    RunContext,
    RunManifest,
    StrictModel,
)
from antenna_ingest.utils.json_io import read_json, write_json


MARKDOWN_CONVERTER_NAME = "nuextract3_markdown"
DOCUMENT_MARKDOWN_PATH = "parsed/document.nuextract.md"
MARKDOWN_REPORT_PATH = "parsed/nuextract_markdown_report.json"
MARKDOWN_PHASE = "nuextract_markdown"
PAGE_MARKER_TEMPLATE = "<!-- page: {page_number} -->"

MARKDOWN_CONVERSION_PROMPT = """
Convert this scientific PDF page image into faithful Markdown.

Preserve headings, paragraphs, equations, figure captions, table content, units, symbols, and numeric values.

Use Markdown for normal text.
Use Markdown or HTML for tables.
Use LaTeX notation for equations when visible.
Return only Markdown.
"""


class MarkdownPageResult(StrictModel):
    page_number: int = Field(ge=1)
    image_path: str = Field(min_length=1)
    markdown_character_count: int = Field(ge=0)


class NuExtractMarkdownReport(StrictModel):
    converter_name: str = Field(min_length=1)
    model: str = Field(min_length=1)
    source_pages_dir: str = Field(min_length=1)
    source_page_render_report: str = Field(min_length=1)
    output_markdown: str = Field(min_length=1)
    page_count: int = Field(ge=1)
    character_count: int = Field(ge=0)
    pages: list[MarkdownPageResult] = Field(min_length=1)
    warnings: list[str] = Field(default_factory=list)


def convert_run_pages_to_markdown(
    run_dir: Path,
    force: bool = False,
    settings: NuExtractSettings | None = None,
    client: object | None = None,
) -> NuExtractMarkdownReport:
    run_dir = Path(run_dir).resolve()
    manifest_path = run_dir / "manifest.json"
    manifest = RunManifest.model_validate(read_json(manifest_path))
    page_render_report = PageRenderReport.model_validate(
        read_json(run_dir / PAGE_RENDER_REPORT_PATH)
    )

    refuse_existing_markdown_outputs(run_dir, force)
    settings = settings or load_nuextract_settings()
    client = client or build_nuextract_client(settings)

    manifest.phase_status[MARKDOWN_PHASE] = PhaseStatus.RUNNING
    write_json(manifest_path, manifest.model_dump(mode="json"))

    try:
        page_markdowns: list[tuple[int, str]] = []
        page_results: list[MarkdownPageResult] = []
        for page in page_render_report.pages:
            image_path = run_dir / page.relative_path
            markdown = request_page_markdown(
                client=client,
                model=settings.ollama_model,
                image_data_url=image_file_to_data_url(image_path),
            )
            markdown = clean_markdown_output(markdown)
            page_markdowns.append((page.page_number, markdown))
            page_results.append(
                MarkdownPageResult(
                    page_number=page.page_number,
                    image_path=page.relative_path,
                    markdown_character_count=len(markdown),
                )
            )

        combined_markdown = combine_page_markdown(page_markdowns)
        markdown_path = run_dir / DOCUMENT_MARKDOWN_PATH
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(combined_markdown, encoding="utf-8")

        report = NuExtractMarkdownReport(
            converter_name=MARKDOWN_CONVERTER_NAME,
            model=settings.ollama_model,
            source_pages_dir=PAGES_DIR,
            source_page_render_report=PAGE_RENDER_REPORT_PATH,
            output_markdown=DOCUMENT_MARKDOWN_PATH,
            page_count=len(page_results),
            character_count=len(combined_markdown),
            pages=page_results,
            warnings=[],
        )
        write_json(run_dir / MARKDOWN_REPORT_PATH, report.model_dump(mode="json"))

        manifest = RunManifest.model_validate(read_json(manifest_path))
        manifest.phase_status[MARKDOWN_PHASE] = PhaseStatus.COMPLETED
        replace_markdown_artifacts(manifest, run_dir)
        write_json(manifest_path, manifest.model_dump(mode="json"))
        return report
    except Exception:
        failed_manifest = RunManifest.model_validate(read_json(manifest_path))
        failed_manifest.phase_status[MARKDOWN_PHASE] = PhaseStatus.FAILED
        write_json(manifest_path, failed_manifest.model_dump(mode="json"))
        raise


def parse_pdf_to_markdown(
    input_pdf: Path,
    runs_root: Path = Path("runs"),
    dpi: int = 170,
    pipeline_version: str = "0.1.0",
    paper_id: str | None = None,
    force: bool = False,
    settings: NuExtractSettings | None = None,
    client: object | None = None,
) -> tuple[RunContext, NuExtractMarkdownReport]:
    context = create_run(
        input_pdf=input_pdf,
        runs_root=runs_root,
        force=force,
        pipeline_version=pipeline_version,
        paper_id=paper_id,
    )
    render_run_pages(context.run_dir, dpi=dpi, force=force)
    report = convert_run_pages_to_markdown(
        context.run_dir,
        force=force,
        settings=settings,
        client=client,
    )
    return context, report


def refuse_existing_markdown_outputs(run_dir: Path, force: bool) -> None:
    markdown_path = Path(run_dir) / DOCUMENT_MARKDOWN_PATH
    report_path = Path(run_dir) / MARKDOWN_REPORT_PATH
    if not force:
        if markdown_path.exists():
            raise FileExistsError(f"NuExtract Markdown already exists: {markdown_path}")
        if report_path.exists():
            raise FileExistsError(f"NuExtract Markdown report already exists: {report_path}")
        return

    if markdown_path.exists():
        markdown_path.unlink()
    if report_path.exists():
        report_path.unlink()


def clean_markdown_output(markdown: str) -> str:
    markdown = re.sub(r"(?:&nbsp;\s*){5,}", " ", markdown)
    markdown = re.sub(r"(?:\u00a0\s*){5,}", " ", markdown)
    markdown = re.sub(r"[ \t]{4,}", " ", markdown)
    return markdown.strip() + "\n"


def request_page_markdown(
    client: object,
    model: str,
    image_data_url: str,
) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": MARKDOWN_CONVERSION_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": image_data_url},
                    },
                ],
            }
        ],
        temperature=0,
        max_tokens=4096,
    )
    content = response.choices[0].message.content
    return content or ""


def combine_page_markdown(page_markdowns: list[tuple[int, str]]) -> str:
    blocks = []
    for page_number, markdown in page_markdowns:
        marker = PAGE_MARKER_TEMPLATE.format(page_number=page_number)
        blocks.append(f"{marker}\n\n{markdown.strip()}")
    return "\n\n".join(blocks) + "\n"


def replace_markdown_artifacts(
    manifest: RunManifest,
    run_dir: Path,
) -> None:
    artifact_names = {"nuextract_markdown", "nuextract_markdown_report"}
    manifest.artifacts = [
        artifact
        for artifact in manifest.artifacts
        if artifact.name not in artifact_names
    ]
    manifest.add_artifact(
        ArtifactReference(
            name="nuextract_markdown",
            relative_path=DOCUMENT_MARKDOWN_PATH,
            producing_phase=MARKDOWN_PHASE,
            checksum=sha256_file(Path(run_dir) / DOCUMENT_MARKDOWN_PATH),
        )
    )
    manifest.add_artifact(
        ArtifactReference(
            name="nuextract_markdown_report",
            relative_path=MARKDOWN_REPORT_PATH,
            producing_phase=MARKDOWN_PHASE,
            checksum=sha256_file(Path(run_dir) / MARKDOWN_REPORT_PATH),
        )
    )
