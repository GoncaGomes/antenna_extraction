from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from antenna_ingest.orchestration.schemas import StrictModel


class LayoutOutputPaths(StrictModel):
    tables: str = Field(min_length=1)
    report: str = Field(min_length=1)


class TableArtifact(StrictModel):
    table_id: str = Field(pattern=r"^tbl_\d{6}$")
    source_document: str = Field(min_length=1)
    docling_ref: str | None = None
    caption: str | None = None
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    markdown: str
    rows: list[dict[str, str | None]]
    row_count: int = Field(ge=0)
    column_count: int = Field(ge=0)
    context_evidence_id: str | None = Field(
        default=None,
        pattern=r"^ev_\d{6}$",
    )
    context_link_method: Literal[
        "page_range_contains_tables",
        "page_range",
    ] | None = None
    quality_status: Literal["usable", "suspect", "rejected"]
    quality_issues: list[str]
    use_for_claim_extraction: bool
    metadata: dict[str, Any]

    @model_validator(mode="after")
    def validate_claim_extraction_flag(self) -> TableArtifact:
        expected = self.quality_status == "usable"
        if self.use_for_claim_extraction != expected:
            raise ValueError(
                "use_for_claim_extraction must be true only for usable tables"
            )
        return self


class TableArtifactDocument(StrictModel):
    paper_id: str | None = None
    source_document: str = Field(min_length=1)
    tables: list[TableArtifact]

    @model_validator(mode="after")
    def validate_tables(self) -> TableArtifactDocument:
        table_ids = [table.table_id for table in self.tables]
        if len(table_ids) != len(set(table_ids)):
            raise ValueError("Duplicate table_id values are not allowed")
        for table in self.tables:
            if table.source_document != self.source_document:
                raise ValueError(
                    "TableArtifact source_document must match document source_document"
                )
        return self


class LayoutReport(StrictModel):
    extractor_name: str = Field(min_length=1)
    extractor_version: str = Field(min_length=1)
    backend: str = Field(min_length=1)
    source_document: str = Field(min_length=1)
    outputs: LayoutOutputPaths
    number_of_tables: int = Field(ge=0)
    number_of_tables_with_markdown: int = Field(ge=0)
    number_of_tables_with_rows: int = Field(ge=0)
    number_of_linked_tables: int = Field(ge=0)
    number_of_unlinked_tables: int = Field(ge=0)
    number_of_usable_tables: int = Field(ge=0)
    number_of_suspect_tables: int = Field(ge=0)
    number_of_rejected_tables: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
