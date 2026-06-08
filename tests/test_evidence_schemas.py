from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from antenna_ingest.evidence.schemas import (
    EvidenceItem,
    EvidenceStoreDocument,
    EvidenceType,
    ParserMetadata,
)


def _parser_metadata() -> ParserMetadata:
    return ParserMetadata(
        parser_name="docling_text_parser",
        parser_version="0.1.0",
        backend="docling",
        backend_version=None,
        created_at=datetime.now(timezone.utc),
        source_format="pdf",
        output_formats=["md", "txt", "docling_json", "evidence_json"],
    )


def _evidence_item(evidence_id: str = "ev_000001") -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        source_document="input/article.pdf",
        type=EvidenceType.paragraph,
        text="A rectangular patch antenna is described.",
        page=1,
        section="Introduction",
        metadata={"backend": "docling"},
    )


def test_valid_evidence_item() -> None:
    item = _evidence_item()

    assert item.evidence_id == "ev_000001"
    assert item.type == EvidenceType.paragraph


def test_invalid_evidence_id_rejected() -> None:
    with pytest.raises(ValidationError):
        _evidence_item("evidence_1")


def test_blank_text_rejected() -> None:
    with pytest.raises(ValidationError):
        EvidenceItem(
            evidence_id="ev_000001",
            source_document="input/article.pdf",
            type=EvidenceType.paragraph,
            text=" ",
        )


def test_page_zero_rejected() -> None:
    with pytest.raises(ValidationError):
        EvidenceItem(
            evidence_id="ev_000001",
            source_document="input/article.pdf",
            type=EvidenceType.paragraph,
            text="Text",
            page=0,
        )


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        EvidenceItem(
            evidence_id="ev_000001",
            source_document="input/article.pdf",
            type=EvidenceType.paragraph,
            text="Text",
            extra_field=True,
        )


def test_valid_evidence_store_document() -> None:
    document = EvidenceStoreDocument(
        paper_id="paper-1",
        source_document="input/article.pdf",
        parser=_parser_metadata(),
        items=[_evidence_item()],
    )

    assert document.items[0].source_document == document.source_document


def test_duplicate_evidence_id_rejected() -> None:
    with pytest.raises(ValidationError):
        EvidenceStoreDocument(
            source_document="input/article.pdf",
            parser=_parser_metadata(),
            items=[_evidence_item("ev_000001"), _evidence_item("ev_000001")],
        )


def test_evidence_store_document_json_round_trip() -> None:
    document = EvidenceStoreDocument(
        source_document="input/article.pdf",
        parser=_parser_metadata(),
        items=[_evidence_item()],
    )

    dumped = document.model_dump(mode="json")
    loaded = EvidenceStoreDocument.model_validate(dumped)

    assert loaded == document
