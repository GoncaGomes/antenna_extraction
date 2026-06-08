from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from antenna_ingest.evidence.schemas import EvidenceType
from antenna_ingest.parsing.docling_evidence_builder import (
    docling_document_to_evidence_items,
)


class FakeLabel(str, Enum):
    TITLE = "title"
    SECTION_HEADER = "section_header"
    TEXT = "text"
    TABLE = "table"
    FORMULA = "formula"
    PAGE_HEADER = "page_header"
    PAGE_FOOTER = "page_footer"
    PICTURE = "picture"


@dataclass
class FakeProvenance:
    page_no: int


@dataclass
class FakeItem:
    label: object
    text: str = ""
    level: int | None = None
    pages: list[int] = field(default_factory=list)
    self_ref: str | None = None
    table_markdown: str = ""
    caption: str = ""

    @property
    def prov(self):
        return [FakeProvenance(page_no=page) for page in self.pages]

    def export_to_markdown(self, _document=None):
        return self.table_markdown

    def caption_text(self):
        return self.caption


class FakeDocument:
    def __init__(self, items):
        self.items = items

    def iterate_items(self):
        yield from self.items


def test_native_builder_groups_sections_and_injects_tables() -> None:
    document = FakeDocument(
        [
            (FakeItem(FakeLabel.PAGE_HEADER, "Journal Header", pages=[1]), 1),
            (FakeItem(FakeLabel.TITLE, "Example Antenna Paper", pages=[1]), 1),
            (FakeItem(FakeLabel.SECTION_HEADER, "Abstract", level=1, pages=[1]), 1),
            (
                FakeItem(
                    FakeLabel.TEXT,
                    "This paper presents a rectangular patch antenna.",
                    pages=[1],
                ),
                2,
            ),
            (FakeItem(FakeLabel.SECTION_HEADER, "2. Analysis", level=1, pages=[2]), 1),
            (
                FakeItem(
                    FakeLabel.TEXT,
                    "The antenna response is evaluated.",
                    pages=[2],
                ),
                2,
            ),
            (
                FakeItem(
                    FakeLabel.TABLE,
                    pages=[2, 3],
                    table_markdown="| Parameter | Value |\n|---|---|\n| Width | 30 mm |",
                ),
                2,
            ),
            (FakeItem(FakeLabel.FORMULA, "f = 2.4 GHz", pages=[3]), 2),
            (
                FakeItem(
                    FakeLabel.PICTURE,
                    pages=[3],
                    caption="Fig. 1 Proposed geometry.",
                ),
                2,
            ),
            (FakeItem(FakeLabel.SECTION_HEADER, "2.1 Results", level=2, pages=[4]), 2),
            (FakeItem(FakeLabel.TEXT, "Measured results are shown.", pages=[4]), 3),
            (FakeItem(FakeLabel.SECTION_HEADER, "References", level=1, pages=[5]), 1),
            (FakeItem(FakeLabel.TEXT, "[1] Example reference.", pages=[5]), 2),
            (FakeItem(FakeLabel.PAGE_FOOTER, "Page 5", pages=[5]), 1),
            (FakeItem(FakeLabel.TEXT, "<!-- image -->", pages=[5]), 1),
        ]
    )

    items = docling_document_to_evidence_items(document, "input/article.pdf")

    assert items[0].type == EvidenceType.title
    assert any(item.type == EvidenceType.abstract for item in items)

    sections = [item for item in items if item.type == EvidenceType.section]
    assert len(sections) == 2
    analysis = sections[0]
    assert "The antenna response is evaluated." in analysis.text
    assert "| Parameter | Value |" in analysis.text
    assert "f = 2.4 GHz" in analysis.text
    assert "Fig. 1 Proposed geometry." in analysis.text
    assert analysis.metadata["contains_tables"] is True
    assert analysis.metadata["table_count"] == 1
    assert analysis.metadata["contains_equations"] is True
    assert analysis.metadata["contains_figures"] is True
    assert analysis.metadata["page_start"] == 2
    assert analysis.metadata["page_end"] == 3
    assert analysis.metadata["section_path"] == ["2. Analysis"]

    subsection = sections[1]
    assert subsection.metadata["section_path"] == ["2. Analysis", "2.1 Results"]
    assert subsection.metadata["heading_level"] == 2

    references = [item for item in items if item.type == EvidenceType.reference]
    assert len(references) == 1
    assert "[1] Example reference." in references[0].text
    assert all("Journal Header" not in item.text for item in items)
    assert all("Page 5" not in item.text for item in items)
    assert all("<!-- image -->" not in item.text for item in items)


def test_native_builder_uses_fallback_paragraph_without_section() -> None:
    document = FakeDocument(
        [(FakeItem(FakeLabel.TEXT, "Preamble text.", pages=[1]), 1)]
    )

    items = docling_document_to_evidence_items(document, "input/article.pdf")

    assert len(items) == 1
    assert items[0].type == EvidenceType.paragraph
    assert items[0].page == 1
