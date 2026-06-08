from __future__ import annotations

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
from antenna_ingest.parsing.schemas import ParseOutputPaths, ParseReport
from antenna_ingest.utils.json_io import read_json, write_json


PARSER_NAME = "docling_text_parser"
PARSER_VERSION = "0.1.0"
MAX_CHARS_PER_EVIDENCE_ITEM = 1200
CHUNK_OVERLAP_CHARS = 150

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
        markdown, text, docling_document, number_of_pages = convert_pdf_with_docling(input_pdf)
        write_text(run_dir / MARKDOWN_PATH, markdown)
        write_text(run_dir / TEXT_PATH, text)
        write_json(run_dir / DOCLING_JSON_PATH, docling_document)

        evidence_items = markdown_to_evidence_items(markdown, source_document)
        evidence_document = EvidenceStoreDocument(
            paper_id=None,
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
            text=text,
            items=evidence_items,
            number_of_pages=number_of_pages,
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


def make_evidence_id(index: int) -> str:
    if index < 1:
        raise ValueError("evidence index must be >= 1")
    return f"ev_{index:06d}"


def write_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def split_long_text(
    text: str,
    max_chars: int = MAX_CHARS_PER_EVIDENCE_ITEM,
    overlap_chars: int = CHUNK_OVERLAP_CHARS,
) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    if overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be smaller than max_chars")

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            split_at = text.rfind(" ", start, end)
            if split_at > start:
                end = split_at
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap_chars, 0)
    return chunks


def infer_evidence_type(block: str, current_section: str | None = None) -> EvidenceType:
    cleaned = block.strip()
    if not cleaned:
        return EvidenceType.unknown
    if cleaned.startswith("#"):
        return EvidenceType.heading
    if current_section and "abstract" in current_section.lower():
        return EvidenceType.abstract
    if cleaned.startswith(("Fig.", "Figure", "TABLE", "Table")):
        return EvidenceType.caption
    if _looks_like_equation(cleaned):
        return EvidenceType.equation
    return EvidenceType.paragraph


def markdown_to_evidence_items(markdown: str, source_document: str) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    current_section: str | None = None
    title_seen = False

    for block in _markdown_blocks(markdown):
        if not _is_meaningful_block(block):
            continue

        if block.startswith("#"):
            heading_text = block.lstrip("#").strip()
            evidence_type = EvidenceType.title if block.startswith("# ") and not title_seen else EvidenceType.heading
            title_seen = title_seen or evidence_type == EvidenceType.title
            section = None
            if evidence_type == EvidenceType.heading:
                current_section = heading_text
            elif "abstract" in heading_text.lower():
                current_section = heading_text
            text = heading_text
        else:
            evidence_type = infer_evidence_type(block, current_section)
            section = current_section
            text = block.strip()

        chunks = split_long_text(text)
        for chunk in chunks:
            chunk_type = EvidenceType.chunk if len(chunks) > 1 and evidence_type == EvidenceType.paragraph else evidence_type
            items.append(
                EvidenceItem(
                    evidence_id=make_evidence_id(len(items) + 1),
                    source_document=source_document,
                    type=chunk_type,
                    text=chunk,
                    page=None,
                    section=section,
                    metadata={
                        "backend": "docling",
                        "source": "markdown_fallback",
                    },
                )
            )

    return items


def convert_pdf_with_docling(pdf_path: Path) -> tuple[str, str, dict[str, Any], int | None]:
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
    return markdown, text, docling_dict, number_of_pages


def _build_parse_report(
    source_document: str,
    text: str,
    items: list[EvidenceItem],
    number_of_pages: int | None,
) -> ParseReport:
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
        warnings=[],
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


def _markdown_blocks(markdown: str) -> list[str]:
    return [block.strip() for block in markdown.split("\n\n") if block.strip()]


def _is_meaningful_block(block: str) -> bool:
    cleaned = block.strip()
    return bool(cleaned) and any(character.isalnum() for character in cleaned)


def _looks_like_equation(text: str) -> bool:
    if "\n" in text:
        return False
    equation_markers = ("=", "\\(", "\\[", "$")
    return any(marker in text for marker in equation_markers) and any(character.isdigit() for character in text)


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
