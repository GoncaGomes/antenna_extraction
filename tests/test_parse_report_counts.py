from __future__ import annotations

from antenna_ingest.evidence.schemas import EvidenceItem, EvidenceType
from antenna_ingest.parsing.docling_text_parser import (
    _count_unique_tables_in_sections,
)


def test_split_section_tables_are_counted_once() -> None:
    sections = [
        _section_item(
            evidence_id=f"ev_{index:06d}",
            section="Antenna Design",
            section_path=["2. Antenna Design"],
            table_count=5,
            split=True,
        )
        for index in range(1, 4)
    ]

    assert _count_unique_tables_in_sections(sections) == 5


def test_tables_from_different_sections_are_summed() -> None:
    sections = [
        _section_item(
            evidence_id="ev_000001",
            section="Antenna Design",
            section_path=["2. Antenna Design"],
            table_count=2,
        ),
        _section_item(
            evidence_id="ev_000002",
            section="Results",
            section_path=["3. Results"],
            table_count=3,
        ),
    ]

    assert _count_unique_tables_in_sections(sections) == 5


def test_sections_without_tables_are_ignored() -> None:
    sections = [
        _section_item(
            evidence_id="ev_000001",
            section="Introduction",
            section_path=["1. Introduction"],
            table_count=0,
        ),
        _section_item(
            evidence_id="ev_000002",
            section="Results",
            section_path=["2. Results"],
            table_count=2,
        ),
    ]

    assert _count_unique_tables_in_sections(sections) == 2


def _section_item(
    *,
    evidence_id: str,
    section: str,
    section_path: list[str],
    table_count: int,
    split: bool = False,
) -> EvidenceItem:
    metadata = {
        "section_path": section_path,
        "heading_level": 1,
        "page_start": 2,
        "page_end": 3,
        "table_count": table_count,
    }
    if split:
        metadata["split_reason"] = "section_too_large"
    return EvidenceItem(
        evidence_id=evidence_id,
        source_document="input/article.pdf",
        type=EvidenceType.section,
        text=f"## {section}\n\nSection content.",
        page=2,
        section=section,
        metadata=metadata,
    )
