from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field, field_validator, model_validator

from antenna_ingest.orchestration.schemas import StrictModel


class EvidenceType(str, Enum):
    title = "title"
    abstract = "abstract"
    heading = "heading"
    paragraph = "paragraph"
    chunk = "chunk"
    caption = "caption"
    equation = "equation"
    table = "table"
    table_row = "table_row"
    figure = "figure"
    reference = "reference"
    unknown = "unknown"


class EvidenceItem(StrictModel):
    evidence_id: str = Field(pattern=r"^ev_\d{6}$")
    source_document: str = Field(min_length=1)
    type: EvidenceType
    text: str = Field(min_length=1)
    page: int | None = Field(default=None, ge=1)
    section: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_text_not_blank(self) -> EvidenceItem:
        if not self.text.strip():
            raise ValueError("EvidenceItem text must not be blank")
        return self


class ParserMetadata(StrictModel):
    parser_name: str = Field(min_length=1)
    parser_version: str = Field(min_length=1)
    backend: str = Field(min_length=1)
    backend_version: str | None = None
    created_at: datetime
    source_format: str = Field(min_length=1)
    output_formats: list[str] = Field(min_length=1)

    @field_validator("source_format")
    @classmethod
    def validate_source_format(cls, value: str) -> str:
        if value != "pdf":
            raise ValueError('source_format must be "pdf"')
        return value


class EvidenceStoreDocument(StrictModel):
    paper_id: str | None = None
    source_document: str = Field(min_length=1)
    parser: ParserMetadata
    items: list[EvidenceItem]

    @model_validator(mode="after")
    def validate_unique_evidence_ids(self) -> EvidenceStoreDocument:
        ids = [item.evidence_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate evidence_id values are not allowed")
        for item in self.items:
            if item.source_document != self.source_document:
                raise ValueError("EvidenceItem source_document must match document source_document")
        return self
