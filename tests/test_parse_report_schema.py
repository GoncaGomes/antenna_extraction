from __future__ import annotations

import pytest
from pydantic import ValidationError

from antenna_ingest.parsing.schemas import ParseOutputPaths, ParseReport


def _outputs() -> ParseOutputPaths:
    return ParseOutputPaths(
        markdown="parsed/document.md",
        text="parsed/document.txt",
        docling_json="parsed/document.docling.json",
        evidence="evidence/evidence_items.json",
    )


def _parse_report(**overrides) -> ParseReport:
    data = {
        "parser_name": "docling_text_parser",
        "parser_version": "0.1.0",
        "backend": "docling",
        "source_document": "input/article.pdf",
        "outputs": _outputs(),
        "number_of_pages": 1,
        "number_of_characters": 100,
        "number_of_evidence_items": 4,
        "number_of_headings": 2,
        "number_of_paragraphs": 1,
        "number_of_captions": 1,
        "number_of_chunks": 0,
        "number_of_sections": 1,
        "number_of_tables_in_sections": 1,
        "number_of_page_ranges_missing": 0,
        "warnings": [],
    }
    data.update(overrides)
    return ParseReport(**data)


def test_valid_parse_report() -> None:
    report = _parse_report()

    assert report.outputs.markdown == "parsed/document.md"


def test_negative_counts_rejected() -> None:
    with pytest.raises(ValidationError):
        _parse_report(number_of_characters=-1)


def test_number_of_pages_zero_rejected() -> None:
    with pytest.raises(ValidationError):
        _parse_report(number_of_pages=0)


@pytest.mark.parametrize(
    "field",
    [
        "number_of_sections",
        "number_of_tables_in_sections",
        "number_of_page_ranges_missing",
    ],
)
def test_negative_native_evidence_counts_rejected(field) -> None:
    with pytest.raises(ValidationError):
        _parse_report(**{field: -1})


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        _parse_report(extra_field=True)


def test_parse_report_json_round_trip() -> None:
    report = _parse_report()

    dumped = report.model_dump(mode="json")
    loaded = ParseReport.model_validate(dumped)

    assert loaded == report
