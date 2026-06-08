from __future__ import annotations

from pydantic import Field

from antenna_ingest.orchestration.schemas import StrictModel


class ParseOutputPaths(StrictModel):
    markdown: str = Field(min_length=1)
    text: str = Field(min_length=1)
    docling_json: str = Field(min_length=1)
    evidence: str = Field(min_length=1)


class ParseReport(StrictModel):
    parser_name: str = Field(min_length=1)
    parser_version: str = Field(min_length=1)
    backend: str = Field(min_length=1)
    source_document: str = Field(min_length=1)
    outputs: ParseOutputPaths
    number_of_pages: int | None = Field(default=None, ge=1)
    number_of_characters: int = Field(ge=0)
    number_of_evidence_items: int = Field(ge=0)
    number_of_headings: int = Field(ge=0)
    number_of_paragraphs: int = Field(ge=0)
    number_of_captions: int = Field(ge=0)
    number_of_chunks: int = Field(ge=0)
    number_of_sections: int = Field(ge=0)
    number_of_tables_in_sections: int = Field(ge=0)
    number_of_page_ranges_missing: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
