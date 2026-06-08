from __future__ import annotations

from antenna_ingest.evidence.schemas import EvidenceType
from antenna_ingest.parsing.docling_text_parser import (
    infer_evidence_type,
    make_evidence_id,
    markdown_to_evidence_items,
    split_long_text,
)


def test_make_evidence_id() -> None:
    assert make_evidence_id(1) == "ev_000001"
    assert make_evidence_id(42) == "ev_000042"


def test_markdown_heading_handling() -> None:
    items = markdown_to_evidence_items("# Title\n\n## Abstract", "input/article.pdf")

    assert items[0].type == EvidenceType.title
    assert items[1].type == EvidenceType.heading


def test_figure_caption_is_caption() -> None:
    assert infer_evidence_type("Fig. 1 Proposed antenna geometry") == EvidenceType.caption


def test_normal_text_is_paragraph() -> None:
    assert infer_evidence_type("A rectangular patch antenna is designed.") == EvidenceType.paragraph


def test_split_long_text_returns_multiple_chunks() -> None:
    text = " ".join(["antenna"] * 400)

    chunks = split_long_text(text, max_chars=200, overlap_chars=20)

    assert len(chunks) > 1


def test_empty_blocks_are_ignored() -> None:
    items = markdown_to_evidence_items("\n\n...\n\nValid paragraph text.", "input/article.pdf")

    assert len(items) == 1
    assert items[0].text == "Valid paragraph text."
