from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from antenna_ingest.evidence.schemas import (
    EvidenceItem,
    EvidenceStoreDocument,
    EvidenceType,
    ParserMetadata,
)
from antenna_ingest.layout.docling_table_extractor import (
    TABLE_EXTRACTOR_NAME,
    TABLE_EXTRACTOR_VERSION,
    extract_table_artifacts,
)
from antenna_ingest.layout.schemas import (
    LayoutOutputPaths,
    LayoutReport,
    TableArtifact,
    TableArtifactDocument,
)
from antenna_ingest.orchestration.runs import sha256_file
from antenna_ingest.orchestration.schemas import ArtifactReference, PhaseStatus, RunManifest
from antenna_ingest.parsing.docling_evidence_builder import (
    docling_document_to_evidence_items,
    markdown_to_evidence_items,
)
from antenna_ingest.parsing.schemas import ParseOutputPaths, ParseReport
from antenna_ingest.utils.json_io import read_json, write_json


PARSER_NAME = "docling_text_parser"
PARSER_VERSION = "0.1.0"
MARKDOWN_FALLBACK_WARNING = (
    "Docling native document unavailable; used Markdown fallback for evidence generation."
)

MARKDOWN_PATH = "parsed/document.md"
TEXT_PATH = "parsed/document.txt"
DOCLING_JSON_PATH = "parsed/document.docling.json"
PARSE_REPORT_PATH = "parsed/parse_report.json"
EVIDENCE_PATH = "evidence/evidence_items.json"
TABLES_PATH = "parsed/tables.json"
LAYOUT_REPORT_PATH = "parsed/layout_report.json"

PHASE_2A_ARTIFACTS = {
    "parsed_markdown": MARKDOWN_PATH,
    "parsed_text": TEXT_PATH,
    "docling_document": DOCLING_JSON_PATH,
    "parse_report": PARSE_REPORT_PATH,
    "evidence_items": EVIDENCE_PATH,
}

PHASE_2B_TABLE_ARTIFACTS = {
    "layout_tables": TABLES_PATH,
    "layout_report": LAYOUT_REPORT_PATH,
}

TABLE_EXTRACTION_SKIPPED_WARNING = (
    "Docling native document unavailable; table extraction skipped."
)


@dataclass
class DoclingParseResult:
    markdown: str
    text: str
    docling_dict: dict[str, Any]
    number_of_pages: int | None
    document: Any | None = None


def parse_run_with_docling(
    run_dir: Path,
    force: bool = False,
) -> ParseReport:
    run_dir = Path(run_dir).resolve()
    manifest_path = run_dir / "manifest.json"
    manifest_data = read_json(manifest_path)
    input_pdf = find_input_pdf(run_dir, manifest_data)
    source_document = input_pdf.relative_to(run_dir).as_posix()

    _refuse_existing_outputs(run_dir, force)
    manifest = RunManifest.model_validate(manifest_data)
    manifest.phase_status.setdefault(
        "layout_enrichment",
        PhaseStatus.PENDING,
    )
    manifest.phase_status["parser_evidence"] = PhaseStatus.RUNNING
    write_json(manifest_path, manifest.model_dump(mode="json"))

    try:
        result = convert_pdf_with_docling(input_pdf)
        write_text(run_dir / MARKDOWN_PATH, result.markdown)
        write_text(run_dir / TEXT_PATH, result.text)
        write_json(run_dir / DOCLING_JSON_PATH, result.docling_dict)

        warnings: list[str] = []
        if result.document is not None:
            evidence_items = docling_document_to_evidence_items(
                result.document,
                source_document,
            )
        else:
            evidence_items = markdown_to_evidence_items(
                result.markdown,
                source_document,
            )
            warnings.append(MARKDOWN_FALLBACK_WARNING)

        evidence_document = EvidenceStoreDocument(
            paper_id=manifest.paper_id,
            source_document=source_document,
            parser=ParserMetadata(
                parser_name=PARSER_NAME,
                parser_version=PARSER_VERSION,
                backend="docling",
                backend_version=_docling_version(),
                created_at=datetime.now(timezone.utc),
                source_format="pdf",
                output_formats=["md", "txt", "docling_json", "evidence_json"],
            ),
            items=evidence_items,
        )
        write_json(run_dir / EVIDENCE_PATH, evidence_document.model_dump(mode="json"))

        manifest.phase_status["layout_enrichment"] = PhaseStatus.RUNNING
        write_json(manifest_path, manifest.model_dump(mode="json"))
        if result.document is not None:
            table_artifacts, layout_warnings = extract_table_artifacts(
                document=result.document,
                source_document=source_document,
                evidence_document=evidence_document,
            )
        else:
            table_artifacts = []
            layout_warnings = [TABLE_EXTRACTION_SKIPPED_WARNING]

        table_document = TableArtifactDocument(
            paper_id=manifest.paper_id,
            source_document=source_document,
            tables=table_artifacts,
        )
        write_json(run_dir / TABLES_PATH, table_document.model_dump(mode="json"))

        layout_report = _build_layout_report(
            source_document=source_document,
            tables=table_artifacts,
            warnings=layout_warnings,
        )
        write_json(
            run_dir / LAYOUT_REPORT_PATH,
            layout_report.model_dump(mode="json"),
        )

        report = _build_parse_report(
            source_document=source_document,
            text=result.text,
            items=evidence_items,
            number_of_pages=result.number_of_pages,
            warnings=warnings,
        )
        write_json(run_dir / PARSE_REPORT_PATH, report.model_dump(mode="json"))

        manifest = RunManifest.model_validate(read_json(manifest_path))
        manifest.phase_status["parser_evidence"] = PhaseStatus.COMPLETED
        manifest.phase_status["layout_enrichment"] = PhaseStatus.COMPLETED
        _replace_phase_2a_artifacts(manifest, run_dir)
        _replace_phase_2b_table_artifacts(manifest, run_dir)
        write_json(manifest_path, manifest.model_dump(mode="json"))
        return report
    except Exception:
        failed_manifest = RunManifest.model_validate(read_json(manifest_path))
        failed_manifest.phase_status["parser_evidence"] = PhaseStatus.FAILED
        if (
            failed_manifest.phase_status.get("layout_enrichment")
            == PhaseStatus.RUNNING
        ):
            failed_manifest.phase_status["layout_enrichment"] = PhaseStatus.FAILED
        write_json(manifest_path, failed_manifest.model_dump(mode="json"))
        raise


def find_input_pdf(run_dir: Path, manifest: dict[str, Any]) -> Path:
    input_file = manifest.get("input_file")
    if isinstance(input_file, str) and input_file:
        pdf_path = Path(run_dir) / input_file
        if pdf_path.exists() and pdf_path.is_file():
            return pdf_path

    input_dir = Path(run_dir) / "input"
    pdfs = sorted(input_dir.glob("*.pdf"))
    if len(pdfs) == 1:
        return pdfs[0]
    if not pdfs:
        raise FileNotFoundError(f"no input PDF found in {input_dir}")
    raise ValueError(f"multiple input PDFs found in {input_dir}; manifest input_file is required")


def write_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def convert_pdf_with_docling(pdf_path: Path) -> DoclingParseResult:
    from docling.document_converter import DocumentConverter

    converter = DocumentConverter()
    result = converter.convert(pdf_path)
    document = result.document

    markdown = document.export_to_markdown()
    text = document.export_to_text()
    docling_dict = document.export_to_dict()
    if not isinstance(docling_dict, dict):
        docling_dict = {"document": docling_dict}

    number_of_pages = _extract_number_of_pages(result, docling_dict)
    return DoclingParseResult(
        markdown=markdown,
        text=text,
        docling_dict=docling_dict,
        number_of_pages=number_of_pages,
        document=document,
    )


def _build_layout_report(
    source_document: str,
    tables: list[TableArtifact],
    warnings: list[str],
) -> LayoutReport:
    number_of_linked_tables = sum(
        table.context_evidence_id is not None
        for table in tables
    )
    return LayoutReport(
        extractor_name=TABLE_EXTRACTOR_NAME,
        extractor_version=TABLE_EXTRACTOR_VERSION,
        backend="docling",
        source_document=source_document,
        outputs=LayoutOutputPaths(
            tables=TABLES_PATH,
            report=LAYOUT_REPORT_PATH,
        ),
        number_of_tables=len(tables),
        number_of_tables_with_markdown=sum(bool(table.markdown) for table in tables),
        number_of_tables_with_rows=sum(bool(table.rows) for table in tables),
        number_of_linked_tables=number_of_linked_tables,
        number_of_unlinked_tables=len(tables) - number_of_linked_tables,
        number_of_usable_tables=sum(
            table.quality_status == "usable"
            for table in tables
        ),
        number_of_suspect_tables=sum(
            table.quality_status == "suspect"
            for table in tables
        ),
        number_of_rejected_tables=sum(
            table.quality_status == "rejected"
            for table in tables
        ),
        warnings=warnings,
    )


def _build_parse_report(
    source_document: str,
    text: str,
    items: list[EvidenceItem],
    number_of_pages: int | None,
    warnings: list[str],
) -> ParseReport:
    sections = [item for item in items if item.type == EvidenceType.section]
    return ParseReport(
        parser_name=PARSER_NAME,
        parser_version=PARSER_VERSION,
        backend="docling",
        source_document=source_document,
        outputs=ParseOutputPaths(
            markdown=MARKDOWN_PATH,
            text=TEXT_PATH,
            docling_json=DOCLING_JSON_PATH,
            evidence=EVIDENCE_PATH,
        ),
        number_of_pages=number_of_pages,
        number_of_characters=len(text),
        number_of_evidence_items=len(items),
        number_of_headings=sum(item.type in {EvidenceType.title, EvidenceType.heading} for item in items),
        number_of_paragraphs=sum(item.type in {EvidenceType.paragraph, EvidenceType.abstract} for item in items),
        number_of_captions=sum(item.type == EvidenceType.caption for item in items),
        number_of_chunks=sum(item.type == EvidenceType.chunk for item in items),
        number_of_sections=len(sections),
        number_of_tables_in_sections=_count_unique_tables_in_sections(sections),
        number_of_page_ranges_missing=sum(
            item.metadata.get("page_start") is None
            or item.metadata.get("page_end") is None
            for item in sections
        ),
        warnings=warnings,
    )


def _count_unique_tables_in_sections(
    sections: list[EvidenceItem],
) -> int:
    table_counts: dict[tuple[Any, ...], int] = {}
    for item in sections:
        try:
            table_count = int(item.metadata.get("table_count", 0))
        except (TypeError, ValueError):
            continue
        if table_count <= 0:
            continue

        section_path = item.metadata.get("section_path", [])
        if not isinstance(section_path, (list, tuple)):
            section_path = [str(section_path)]
        key = (
            tuple(section_path),
            item.section,
            item.metadata.get("heading_level"),
            item.metadata.get("page_start"),
            item.metadata.get("page_end"),
        )
        table_counts[key] = max(table_counts.get(key, 0), table_count)
    return sum(table_counts.values())


def _replace_phase_2a_artifacts(manifest: RunManifest, run_dir: Path) -> None:
    artifact_names = set(PHASE_2A_ARTIFACTS)
    manifest.artifacts = [
        artifact
        for artifact in manifest.artifacts
        if artifact.name not in artifact_names
    ]
    for name, relative_path in PHASE_2A_ARTIFACTS.items():
        manifest.add_artifact(
            ArtifactReference(
                name=name,
                relative_path=relative_path,
                producing_phase="parser_evidence",
                checksum=sha256_file(run_dir / relative_path),
            )
        )


def _replace_phase_2b_table_artifacts(
    manifest: RunManifest,
    run_dir: Path,
) -> None:
    artifact_names = set(PHASE_2B_TABLE_ARTIFACTS)
    manifest.artifacts = [
        artifact
        for artifact in manifest.artifacts
        if artifact.name not in artifact_names
    ]
    for name, relative_path in PHASE_2B_TABLE_ARTIFACTS.items():
        manifest.add_artifact(
            ArtifactReference(
                name=name,
                relative_path=relative_path,
                producing_phase="layout_enrichment",
                checksum=sha256_file(run_dir / relative_path),
            )
        )


def _refuse_existing_outputs(run_dir: Path, force: bool) -> None:
    if force:
        return
    output_paths = [
        *PHASE_2A_ARTIFACTS.values(),
        *PHASE_2B_TABLE_ARTIFACTS.values(),
    ]
    existing = [
        relative_path
        for relative_path in output_paths
        if (run_dir / relative_path).exists()
    ]
    if existing:
        raise FileExistsError(f"Parsing output already exists: {existing[0]}")


def _extract_number_of_pages(result: Any, docling_dict: dict[str, Any]) -> int | None:
    pages = getattr(result, "pages", None)
    if isinstance(pages, list) and pages:
        return len(pages)

    document = getattr(result, "document", None)
    document_pages = getattr(document, "pages", None)
    if isinstance(document_pages, dict) and document_pages:
        return len(document_pages)
    if isinstance(document_pages, list) and document_pages:
        return len(document_pages)

    dict_pages = docling_dict.get("pages")
    if isinstance(dict_pages, dict) and dict_pages:
        return len(dict_pages)
    if isinstance(dict_pages, list) and dict_pages:
        return len(dict_pages)
    return None


def _docling_version() -> str | None:
    try:
        return version("docling")
    except PackageNotFoundError:
        return None
