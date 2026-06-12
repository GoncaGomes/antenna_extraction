from __future__ import annotations

import pytest
from pydantic import ValidationError

from antenna_ingest.layout.schemas import (
    LayoutOutputPaths,
    LayoutReport,
    TableArtifact,
    TableArtifactDocument,
)


def _table_artifact(table_id: str = "tbl_000001") -> TableArtifact:
    return TableArtifact(
        table_id=table_id,
        source_document="input/article.pdf",
        docling_ref="#/tables/0",
        caption="Table 1. Antenna dimensions.",
        page_start=2,
        page_end=2,
        markdown="| Parameter | Value |\n|---|---|\n| Width | 30 mm |",
        rows=[{"Parameter": "Width", "Value": "30 mm"}],
        row_count=1,
        column_count=2,
        context_evidence_id="ev_000003",
        context_link_method="page_range_contains_tables",
        metadata={
            "backend": "docling",
            "self_ref": "#/tables/0",
            "has_dataframe": True,
            "has_markdown": True,
        },
    )


def _layout_report(**overrides) -> LayoutReport:
    data = {
        "extractor_name": "docling_table_extractor",
        "extractor_version": "0.1.0",
        "backend": "docling",
        "source_document": "input/article.pdf",
        "outputs": LayoutOutputPaths(
            tables="parsed/tables.json",
            report="parsed/layout_report.json",
        ),
        "number_of_tables": 1,
        "number_of_tables_with_markdown": 1,
        "number_of_tables_with_rows": 1,
        "number_of_linked_tables": 1,
        "number_of_unlinked_tables": 0,
        "warnings": [],
    }
    data.update(overrides)
    return LayoutReport(**data)


def test_valid_table_artifact() -> None:
    table = _table_artifact()

    assert table.table_id == "tbl_000001"
    assert table.row_count == 1


def test_invalid_table_id_rejected() -> None:
    with pytest.raises(ValidationError):
        _table_artifact("table_1")


def test_page_start_zero_rejected() -> None:
    with pytest.raises(ValidationError):
        TableArtifact.model_validate(
            {
                **_table_artifact().model_dump(),
                "page_start": 0,
            }
        )


def test_duplicate_table_id_rejected() -> None:
    with pytest.raises(ValidationError):
        TableArtifactDocument(
            source_document="input/article.pdf",
            tables=[_table_artifact(), _table_artifact()],
        )


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        TableArtifact(
            **_table_artifact().model_dump(),
            extra_field=True,
        )


@pytest.mark.parametrize(
    "field",
    [
        "number_of_tables",
        "number_of_tables_with_markdown",
        "number_of_tables_with_rows",
        "number_of_linked_tables",
        "number_of_unlinked_tables",
    ],
)
def test_layout_report_rejects_negative_counts(field) -> None:
    with pytest.raises(ValidationError):
        _layout_report(**{field: -1})


def test_layout_document_and_report_json_round_trip() -> None:
    document = TableArtifactDocument(
        paper_id="paper-1",
        source_document="input/article.pdf",
        tables=[_table_artifact()],
    )
    report = _layout_report()

    loaded_document = TableArtifactDocument.model_validate(
        document.model_dump(mode="json")
    )
    loaded_report = LayoutReport.model_validate(report.model_dump(mode="json"))

    assert loaded_document == document
    assert loaded_report == report
