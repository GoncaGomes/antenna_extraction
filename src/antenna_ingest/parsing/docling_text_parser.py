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

PHASE_2A_ARTIFACTS = {
    "parsed_markdown": MARKDOWN_PATH,
    "parsed_text": TEXT_PATH,
    "docling_document": DOCLING_JSON_PATH,
    "parse_report": PARSE_REPORT_PATH,
    "evidence_items": EVIDENCE_PATH,
}


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
        _replace_phase_2a_artifacts(manifest, run_dir)
        write_json(manifest_path, manifest.model_dump(mode="json"))
        return report
    except Exception:
        failed_manifest = RunManifest.model_validate(read_json(manifest_path))
        failed_manifest.phase_status["parser_evidence"] = PhaseStatus.FAILED
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
        number_of_tables_in_sections=sum(
            int(item.metadata.get("table_count", 0))
            for item in sections
        ),
        number_of_page_ranges_missing=sum(
            item.metadata.get("page_start") is None
            or item.metadata.get("page_end") is None
            for item in sections
        ),
        warnings=warnings,
    )


def _replace_phase_2a_artifacts(manifest: RunManifest, run_dir: Path) -> None:
    artifact_names = set(PHASE_2A_ARTIFACTS)
    manifest.artifacts = [artifact for artifact in manifest.artifacts if artifact.name not in artifact_names]
    for name, relative_path in PHASE_2A_ARTIFACTS.items():
        manifest.add_artifact(
            ArtifactReference(
                name=name,
                relative_path=relative_path,
                producing_phase="parser_evidence",
                checksum=sha256_file(run_dir / relative_path),
            )
        )


def _refuse_existing_outputs(run_dir: Path, force: bool) -> None:
    if force:
        return
    existing = [relative_path for relative_path in PHASE_2A_ARTIFACTS.values() if (run_dir / relative_path).exists()]
    if existing:
        raise FileExistsError(f"Phase 2A output already exists: {existing[0]}")


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
