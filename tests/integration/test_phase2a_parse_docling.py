from __future__ import annotations

import pytest

import antenna_ingest.parsing.docling_text_parser as parser
from antenna_ingest.evidence.schemas import EvidenceStoreDocument, EvidenceType
from antenna_ingest.orchestration.runs import create_run
from antenna_ingest.orchestration.schemas import RunManifest
from antenna_ingest.parsing.docling_text_parser import parse_run_with_docling
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
    assert evidence_document.items

    evidence_ids = [item.evidence_id for item in evidence_document.items]
    assert len(evidence_ids) == len(set(evidence_ids))
    evidence_types = {item.type for item in evidence_document.items}
    assert evidence_types & {EvidenceType.title, EvidenceType.heading}
    assert evidence_types & {EvidenceType.paragraph, EvidenceType.abstract}
    assert EvidenceType.caption in evidence_types

    parse_report = ParseReport.model_validate(read_json(run_dir / "parsed/parse_report.json"))
    assert parse_report.number_of_evidence_items == len(evidence_document.items)
    assert report.number_of_evidence_items == len(evidence_document.items)


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


def _create_test_run(tmp_path):
    article_pdf = tmp_path / "article.pdf"
    article_pdf.write_bytes(b"%PDF-1.4\n%fake test pdf\n")
    return create_run(article_pdf, runs_root=tmp_path / "runs").run_dir


def _fake_convert_pdf_with_docling(_pdf_path):
    return MARKDOWN, TEXT, {"mock": True, "name": "Example Antenna Paper"}, 1
