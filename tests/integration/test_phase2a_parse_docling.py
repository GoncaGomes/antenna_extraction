from __future__ import annotations

from dataclasses import dataclass, field

import pytest

import antenna_ingest.parsing.docling_text_parser as parser
from antenna_ingest.evidence.schemas import EvidenceStoreDocument, EvidenceType
from antenna_ingest.orchestration.runs import create_run
from antenna_ingest.orchestration.schemas import RunManifest
from antenna_ingest.parsing.docling_text_parser import (
    MARKDOWN_FALLBACK_WARNING,
    DoclingParseResult,
    parse_run_with_docling,
)
from antenna_ingest.parsing.schemas import ParseReport
from antenna_ingest.utils.json_io import read_json


MARKDOWN = """# Example Antenna Paper

## Abstract

This paper presents a rectangular microstrip patch antenna.

## I. Introduction

A rectangular patch antenna is designed on an FR-4 substrate.

Fig. 1 Proposed antenna geometry.
"""

TEXT = """Example Antenna Paper

Abstract

This paper presents a rectangular microstrip patch antenna.

I. Introduction

A rectangular patch antenna is designed on an FR-4 substrate.

Fig. 1 Proposed antenna geometry.
"""


def test_phase2a_parse_docling_creates_outputs_and_updates_manifest(tmp_path, monkeypatch) -> None:
    run_dir = _create_test_run(tmp_path)
    monkeypatch.setattr(parser, "convert_pdf_with_docling", _fake_convert_pdf_with_docling)

    report = parse_run_with_docling(run_dir, force=False)

    assert (run_dir / "parsed/document.md").exists()
    assert (run_dir / "parsed/document.txt").exists()
    assert (run_dir / "parsed/document.docling.json").exists()
    assert (run_dir / "parsed/parse_report.json").exists()
    assert (run_dir / "evidence/evidence_items.json").exists()

    manifest = RunManifest.model_validate(read_json(run_dir / "manifest.json"))
    assert manifest.phase_status["parser_evidence"] == "completed"
    artifact_names = {artifact.name for artifact in manifest.artifacts}
    assert "parsed_markdown" in artifact_names
    assert "parsed_text" in artifact_names
    assert "docling_document" in artifact_names
    assert "parse_report" in artifact_names
    assert "evidence_items" in artifact_names
    assert all(artifact.checksum for artifact in manifest.artifacts if artifact.name in artifact_names)

    evidence_data = read_json(run_dir / "evidence/evidence_items.json")
    evidence_document = EvidenceStoreDocument.model_validate(evidence_data)
    assert evidence_document.parser.parser_name == "docling_text_parser"
    assert evidence_document.paper_id == "example_paper"
    assert evidence_document.items

    evidence_ids = [item.evidence_id for item in evidence_document.items]
    assert len(evidence_ids) == len(set(evidence_ids))
    evidence_types = {item.type for item in evidence_document.items}
    assert EvidenceType.title in evidence_types
    assert EvidenceType.abstract in evidence_types
    assert EvidenceType.section in evidence_types
    section_items = [
        item for item in evidence_document.items if item.type == EvidenceType.section
    ]
    assert any("| Parameter | Value |" in item.text for item in section_items)
    assert any(item.metadata["page_start"] == 2 for item in section_items)

    parse_report = ParseReport.model_validate(read_json(run_dir / "parsed/parse_report.json"))
    assert parse_report.number_of_evidence_items == len(evidence_document.items)
    assert report.number_of_evidence_items == len(evidence_document.items)
    assert parse_report.number_of_sections == len(section_items)
    assert parse_report.number_of_tables_in_sections == 1
    assert parse_report.number_of_page_ranges_missing == 0
    assert parse_report.warnings == []


def test_phase2a_parse_docling_refuses_existing_outputs_without_force(tmp_path, monkeypatch) -> None:
    run_dir = _create_test_run(tmp_path)
    monkeypatch.setattr(parser, "convert_pdf_with_docling", _fake_convert_pdf_with_docling)
    parse_run_with_docling(run_dir, force=False)

    with pytest.raises(FileExistsError):
        parse_run_with_docling(run_dir, force=False)


def test_phase2a_parse_docling_allows_existing_outputs_with_force(tmp_path, monkeypatch) -> None:
    run_dir = _create_test_run(tmp_path)
    monkeypatch.setattr(parser, "convert_pdf_with_docling", _fake_convert_pdf_with_docling)
    parse_run_with_docling(run_dir, force=False)

    report = parse_run_with_docling(run_dir, force=True)

    assert report.number_of_pages == 1


def test_phase2a_parse_docling_uses_markdown_fallback(tmp_path, monkeypatch) -> None:
    run_dir = _create_test_run(tmp_path)
    monkeypatch.setattr(parser, "convert_pdf_with_docling", _fake_fallback_conversion)

    report = parse_run_with_docling(run_dir)
    evidence = EvidenceStoreDocument.model_validate(
        read_json(run_dir / "evidence/evidence_items.json")
    )

    assert MARKDOWN_FALLBACK_WARNING in report.warnings
    assert evidence.items
    assert all(
        item.metadata["source"] == "markdown_fallback"
        for item in evidence.items
    )


def _create_test_run(tmp_path):
    article_pdf = tmp_path / "article.pdf"
    article_pdf.write_bytes(b"%PDF-1.4\n%fake test pdf\n")
    return create_run(
        article_pdf,
        runs_root=tmp_path / "runs",
        paper_id="example_paper",
    ).run_dir


def _fake_convert_pdf_with_docling(_pdf_path):
    return DoclingParseResult(
        markdown=MARKDOWN,
        text=TEXT,
        docling_dict={"mock": True, "name": "Example Antenna Paper"},
        number_of_pages=1,
        document=_fake_native_document(),
    )


def _fake_fallback_conversion(_pdf_path):
    return DoclingParseResult(
        markdown=MARKDOWN,
        text=TEXT,
        docling_dict={"mock": True, "name": "Example Antenna Paper"},
        number_of_pages=1,
        document=None,
    )


@dataclass
class _FakeProvenance:
    page_no: int


@dataclass
class _FakeItem:
    label: str
    text: str = ""
    level: int | None = None
    pages: list[int] = field(default_factory=list)
    table_markdown: str = ""
    self_ref: str | None = None

    @property
    def prov(self):
        return [_FakeProvenance(page) for page in self.pages]

    def export_to_markdown(self, _document=None):
        return self.table_markdown


class _FakeDocument:
    def __init__(self, items):
        self.items = items

    def iterate_items(self):
        yield from self.items


def _fake_native_document():
    return _FakeDocument(
        [
            (_FakeItem("title", "Example Antenna Paper", pages=[1]), 1),
            (_FakeItem("section_header", "Abstract", level=1, pages=[1]), 1),
            (
                _FakeItem(
                    "text",
                    "This paper presents a rectangular microstrip patch antenna.",
                    pages=[1],
                ),
                2,
            ),
            (
                _FakeItem(
                    "section_header",
                    "I. Introduction",
                    level=1,
                    pages=[2],
                ),
                1,
            ),
            (
                _FakeItem(
                    "text",
                    "A rectangular patch antenna is designed on an FR-4 substrate.",
                    pages=[2],
                ),
                2,
            ),
            (
                _FakeItem(
                    "table",
                    pages=[2],
                    table_markdown="| Parameter | Value |\n|---|---|\n| Width | 30 mm |",
                ),
                2,
            ),
        ]
    )
