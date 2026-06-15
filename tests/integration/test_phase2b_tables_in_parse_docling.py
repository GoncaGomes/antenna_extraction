from __future__ import annotations

from dataclasses import dataclass

import pytest

import antenna_ingest.parsing.docling_text_parser as parser
from antenna_ingest.layout.schemas import LayoutReport, TableArtifactDocument
from antenna_ingest.orchestration.runs import create_run
from antenna_ingest.orchestration.schemas import RunManifest
from antenna_ingest.parsing.docling_text_parser import (
    DoclingParseResult,
    parse_run_with_docling,
)
from antenna_ingest.utils.json_io import read_json


@dataclass
class FakeProvenance:
    page_no: int


class FakeDataFrame:
    shape = (1, 2)

    def to_dict(self, orient):
        assert orient == "records"
        return [{"Parameter": "Width", "Value": "30 mm"}]


class FakeTable:
    self_ref = "#/tables/0"
    prov = [FakeProvenance(2)]

    def caption_text(self, doc=None):
        return "Table 1. Antenna dimensions."

    def export_to_markdown(self, doc=None):
        return "| Parameter | Value |\n|---|---|\n| Width | 30 mm |"

    def export_to_dataframe(self, doc=None):
        return FakeDataFrame()


class FakeItem:
    def __init__(self, label, text="", level=None, pages=None, table=None):
        self.label = label
        self.text = text
        self.level = level
        self.prov = [FakeProvenance(page) for page in (pages or [])]
        self.self_ref = getattr(table, "self_ref", None)
        self._table = table

    def export_to_markdown(self, doc=None):
        return self._table.export_to_markdown(doc=doc)


class FakeDocument:
    def __init__(self):
        table = FakeTable()
        self.tables = [table]
        self.items = [
            (FakeItem("title", "Example Antenna Paper", pages=[1]), 1),
            (
                FakeItem(
                    "section_header",
                    "I. Antenna Design",
                    level=1,
                    pages=[2],
                ),
                1,
            ),
            (
                FakeItem(
                    "text",
                    "The antenna dimensions are listed below.",
                    pages=[2],
                ),
                2,
            ),
            (FakeItem("table", pages=[2], table=table), 2),
        ]

    def iterate_items(self):
        yield from self.items


def test_parse_docling_writes_phase2b_table_artifacts(tmp_path, monkeypatch) -> None:
    run_dir = _create_run(tmp_path)
    conversion_calls = 0

    def fake_conversion(_pdf_path):
        nonlocal conversion_calls
        conversion_calls += 1
        return DoclingParseResult(
            markdown="# Example Antenna Paper",
            text="Example Antenna Paper",
            docling_dict={"mock": True},
            number_of_pages=2,
            document=FakeDocument(),
        )

    monkeypatch.setattr(parser, "convert_pdf_with_docling", fake_conversion)

    parse_run_with_docling(run_dir)

    assert conversion_calls == 1
    for relative_path in (
        "parsed/document.md",
        "parsed/document.txt",
        "parsed/document.docling.json",
        "parsed/parse_report.json",
        "evidence/evidence_items.json",
        "parsed/tables.json",
        "parsed/layout_report.json",
    ):
        assert (run_dir / relative_path).exists()

    tables = TableArtifactDocument.model_validate(
        read_json(run_dir / "parsed/tables.json")
    )
    report = LayoutReport.model_validate(
        read_json(run_dir / "parsed/layout_report.json")
    )
    assert len(tables.tables) == 1
    assert tables.tables[0].context_evidence_id is not None
    assert tables.tables[0].quality_status == "usable"
    assert tables.tables[0].quality_issues == []
    assert tables.tables[0].use_for_claim_extraction is True
    assert report.number_of_tables == 1
    assert report.number_of_linked_tables == 1
    assert report.number_of_usable_tables == 1
    assert report.number_of_suspect_tables == 0
    assert report.number_of_rejected_tables == 0

    manifest = RunManifest.model_validate(read_json(run_dir / "manifest.json"))
    assert manifest.phase_status["parser_evidence"] == "completed"
    assert manifest.phase_status["layout_enrichment"] == "completed"
    layout_artifacts = {
        artifact.name: artifact
        for artifact in manifest.artifacts
        if artifact.name in {"layout_tables", "layout_report"}
    }
    assert set(layout_artifacts) == {"layout_tables", "layout_report"}
    assert all(artifact.checksum for artifact in layout_artifacts.values())


def test_phase2b_outputs_follow_force_behavior(tmp_path, monkeypatch) -> None:
    run_dir = _create_run(tmp_path)
    monkeypatch.setattr(parser, "convert_pdf_with_docling", _fake_conversion)
    parse_run_with_docling(run_dir)

    with pytest.raises(FileExistsError):
        parse_run_with_docling(run_dir)

    (run_dir / "parsed/tables.json").write_text("stale", encoding="utf-8")
    parse_run_with_docling(run_dir, force=True)

    tables = TableArtifactDocument.model_validate(
        read_json(run_dir / "parsed/tables.json")
    )
    assert len(tables.tables) == 1


def test_table_extraction_failure_updates_manifest(tmp_path, monkeypatch) -> None:
    run_dir = _create_run(tmp_path)
    monkeypatch.setattr(parser, "convert_pdf_with_docling", _fake_conversion)

    def fail_extraction(**_kwargs):
        raise RuntimeError("table extraction failed")

    monkeypatch.setattr(parser, "extract_table_artifacts", fail_extraction)

    with pytest.raises(RuntimeError, match="table extraction failed"):
        parse_run_with_docling(run_dir)

    manifest = RunManifest.model_validate(read_json(run_dir / "manifest.json"))
    assert manifest.phase_status["parser_evidence"] == "failed"
    assert manifest.phase_status["layout_enrichment"] == "failed"


def _create_run(tmp_path):
    article_pdf = tmp_path / "article.pdf"
    article_pdf.write_bytes(b"%PDF-1.4\n%fake test pdf\n")
    return create_run(article_pdf, runs_root=tmp_path / "runs").run_dir


def _fake_conversion(_pdf_path):
    return DoclingParseResult(
        markdown="# Example Antenna Paper",
        text="Example Antenna Paper",
        docling_dict={"mock": True},
        number_of_pages=2,
        document=FakeDocument(),
    )
