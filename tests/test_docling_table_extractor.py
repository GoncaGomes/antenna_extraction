from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from antenna_ingest.evidence.schemas import (
    EvidenceItem,
    EvidenceStoreDocument,
    EvidenceType,
    ParserMetadata,
)
from antenna_ingest.layout.docling_table_extractor import (
    extract_table_artifacts,
    link_table_to_context_evidence,
    make_table_id,
)


@dataclass
class FakeProvenance:
    page_no: int


class FakeDataFrame:
    def __init__(self, records, columns):
        self.records = records
        self.shape = (len(records), columns)

    def to_dict(self, orient):
        assert orient == "records"
        return self.records


class FakeTable:
    def __init__(
        self,
        *,
        self_ref="#/tables/0",
        pages=(2, 3),
        caption="Table 1. Antenna dimensions.",
        markdown="| Parameter | Value |\n|---|---|\n| Width | 30 mm |",
        dataframe=None,
        fail_markdown=False,
        fail_dataframe=False,
    ):
        self.self_ref = self_ref
        self.prov = [FakeProvenance(page) for page in pages]
        self._caption = caption
        self._markdown = markdown
        self._dataframe = dataframe or FakeDataFrame(
            [{"Parameter": "Width", "Value": 30, "Note": None}],
            columns=3,
        )
        self._fail_markdown = fail_markdown
        self._fail_dataframe = fail_dataframe

    def caption_text(self, doc=None):
        return self._caption

    def export_to_markdown(self, doc=None):
        if self._fail_markdown:
            raise RuntimeError("markdown failed")
        return self._markdown

    def export_to_dataframe(self, doc=None):
        if self._fail_dataframe:
            raise RuntimeError("dataframe failed")
        return self._dataframe


class FakeDocument:
    def __init__(self, tables=None):
        self.tables = tables


def test_make_table_id() -> None:
    assert make_table_id(1) == "tbl_000001"


def test_make_table_id_rejects_invalid_index() -> None:
    try:
        make_table_id(0)
    except ValueError:
        pass
    else:
        raise AssertionError("make_table_id should reject indexes below one")


def test_extract_table_artifact_uses_native_exports() -> None:
    document = FakeDocument([FakeTable()])

    artifacts, warnings = extract_table_artifacts(
        document,
        "input/article.pdf",
    )

    assert len(artifacts) == 1
    table = artifacts[0]
    assert table.table_id == "tbl_000001"
    assert table.docling_ref == "#/tables/0"
    assert table.caption == "Table 1. Antenna dimensions."
    assert table.page_start == 2
    assert table.page_end == 3
    assert "| Parameter | Value |" in table.markdown
    assert table.rows == [
        {"Parameter": "Width", "Value": "30", "Note": None}
    ]
    assert table.row_count == 1
    assert table.column_count == 3
    assert table.metadata["backend"] == "docling"
    assert table.metadata["has_dataframe"] is True
    assert table.metadata["has_markdown"] is True
    assert "Table tbl_000001: no context evidence link found." in warnings


def test_dataframe_export_failure_is_graceful() -> None:
    document = FakeDocument([FakeTable(fail_dataframe=True)])

    artifacts, warnings = extract_table_artifacts(
        document,
        "input/article.pdf",
    )

    table = artifacts[0]
    assert table.rows == []
    assert table.row_count == 0
    assert table.column_count == 0
    assert table.metadata["has_dataframe"] is False
    assert "Table tbl_000001: dataframe export failed." in warnings


def test_markdown_export_failure_is_graceful() -> None:
    document = FakeDocument([FakeTable(fail_markdown=True)])

    artifacts, warnings = extract_table_artifacts(
        document,
        "input/article.pdf",
    )

    table = artifacts[0]
    assert table.markdown == ""
    assert table.metadata["has_markdown"] is False
    assert "Table tbl_000001: markdown export failed." in warnings
    assert "Table tbl_000001: markdown is empty." in warnings


def test_missing_document_tables_is_empty() -> None:
    artifacts, warnings = extract_table_artifacts(
        FakeDocument(None),
        "input/article.pdf",
    )

    assert artifacts == []
    assert warnings == []


def test_table_links_to_preferred_section_evidence() -> None:
    evidence_document = _evidence_document(
        [
            _section_item(
                "ev_000001",
                page_start=2,
                page_end=4,
                contains_tables=False,
            ),
            _section_item(
                "ev_000002",
                page_start=3,
                page_end=3,
                contains_tables=True,
            ),
        ]
    )

    evidence_id, method = link_table_to_context_evidence(
        3,
        evidence_document,
    )

    assert evidence_id == "ev_000002"
    assert method == "page_range_contains_tables"


def test_table_links_to_page_range_when_no_table_section_exists() -> None:
    evidence_document = _evidence_document(
        [
            _section_item(
                "ev_000001",
                page_start=2,
                page_end=4,
                contains_tables=False,
            )
        ]
    )

    evidence_id, method = link_table_to_context_evidence(
        3,
        evidence_document,
    )

    assert evidence_id == "ev_000001"
    assert method == "page_range"


def test_unlinked_table_returns_none_and_warning() -> None:
    evidence_document = _evidence_document(
        [
            _section_item(
                "ev_000001",
                page_start=1,
                page_end=2,
                contains_tables=True,
            )
        ]
    )

    artifacts, warnings = extract_table_artifacts(
        FakeDocument([FakeTable(pages=(5,))]),
        "input/article.pdf",
        evidence_document,
    )

    assert artifacts[0].context_evidence_id is None
    assert artifacts[0].context_link_method is None
    assert "Table tbl_000001: no context evidence link found." in warnings


def _section_item(
    evidence_id,
    *,
    page_start,
    page_end,
    contains_tables,
):
    return EvidenceItem(
        evidence_id=evidence_id,
        source_document="input/article.pdf",
        type=EvidenceType.section,
        text="## Antenna Design\n\nSection content.",
        page=page_start,
        section="Antenna Design",
        metadata={
            "page_start": page_start,
            "page_end": page_end,
            "contains_tables": contains_tables,
            "table_count": 1 if contains_tables else 0,
        },
    )


def _evidence_document(items):
    return EvidenceStoreDocument(
        source_document="input/article.pdf",
        parser=ParserMetadata(
            parser_name="docling_text_parser",
            parser_version="0.1.0",
            backend="docling",
            created_at=datetime.now(timezone.utc),
            source_format="pdf",
            output_formats=["evidence_json"],
        ),
        items=items,
    )
