from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from antenna_ingest.evidence.schemas import EvidenceItem, EvidenceType


MAX_SECTION_CHARS = 10_000
SECTION_SPLIT_OVERLAP_CHARS = 200

_IGNORED_LABELS = {"page_header", "page_footer"}
_PICTURE_LABELS = {"picture", "image", "chart"}
_TEXT_LABELS = {"paragraph", "text", "list_item"}
_EQUATION_LABELS = {"formula", "equation"}
_NOISY_ISOLATED_TEXT = {
    "article",
    "proceeding paper",
    "paper · open access",
    "paper • open access",
    "paper open access",
    "you may also like",
    "view the article online for updates and enhancements",
}
_NOISY_TEXT_PREFIXES = {
    "academic editors:",
    "citation:",
    "content from this work may be used under the terms",
    "copyright:",
    "licensee mdpi",
    "published under licence",
    "published under license",
    "published:",
    "this content was downloaded from",
    "to cite this article",
}


@dataclass
class _SectionAccumulator:
    heading: str
    section_path: list[str]
    heading_level: int
    evidence_type: EvidenceType = EvidenceType.section
    parts: list[str] = field(default_factory=list)
    pages: list[int] = field(default_factory=list)
    table_count: int = 0
    contains_equations: bool = False
    contains_figures: bool = False


def docling_document_to_evidence_items(
    document: Any,
    source_document: str,
) -> list[EvidenceItem]:
    drafts: list[dict[str, Any]] = []
    active_section: _SectionAccumulator | None = None
    section_stack: list[tuple[int, str]] = []

    for item, iterator_level in document.iterate_items():
        label = normalize_label(getattr(item, "label", None))
        text = _item_text(item)
        pages = _item_pages(item)

        if label in _IGNORED_LABELS:
            continue
        if label == "title":
            if _is_meaningful_text(text):
                drafts.append(
                    _draft(
                        evidence_type=EvidenceType.title,
                        text=text,
                        page=min(pages) if pages else None,
                        section=None,
                        metadata=_base_metadata(item, pages),
                    )
                )
            continue
        if label == "section_header":
            active_section = _flush_section(active_section, drafts)
            if not _is_meaningful_text(text):
                continue
            heading_level = _heading_level(item, iterator_level)
            section_stack = [
                (level, heading)
                for level, heading in section_stack
                if level < heading_level
            ]
            section_stack.append((heading_level, text))
            evidence_type = _section_evidence_type(text)
            active_section = _SectionAccumulator(
                heading=text,
                section_path=[heading for _, heading in section_stack],
                heading_level=heading_level,
                evidence_type=evidence_type,
                pages=list(pages),
            )
            continue
        if label in _IGNORED_LABELS or _is_placeholder(text):
            continue
        if label == "table":
            table_markdown = _table_markdown(item, document)
            if active_section is not None and _is_meaningful_text(table_markdown):
                active_section.parts.append(table_markdown)
                active_section.pages.extend(pages)
                active_section.table_count += 1
            continue
        if label in _PICTURE_LABELS:
            caption = _caption_text(item, document)
            if active_section is not None:
                active_section.contains_figures = True
                active_section.pages.extend(pages)
                if _is_meaningful_text(caption):
                    active_section.parts.append(caption)
            continue
        if label in _EQUATION_LABELS:
            if active_section is not None and _is_meaningful_text(text):
                active_section.parts.append(text)
                active_section.pages.extend(pages)
                active_section.contains_equations = True
            elif _is_meaningful_text(text):
                drafts.append(_fallback_draft(item, text, pages, EvidenceType.equation))
            continue
        if label == "caption":
            if active_section is not None and _is_meaningful_text(text):
                active_section.parts.append(text)
                active_section.pages.extend(pages)
            elif _is_meaningful_text(text):
                drafts.append(_fallback_draft(item, text, pages, EvidenceType.caption))
            continue
        if label == "reference" and active_section is None and _is_meaningful_text(text):
            drafts.append(_fallback_draft(item, text, pages, EvidenceType.reference))
            continue
        if label in _TEXT_LABELS or not label:
            if not _is_meaningful_text(text):
                continue
            if _looks_like_inline_abstract(text):
                drafts.append(_fallback_draft(item, text, pages, EvidenceType.abstract))
            elif active_section is not None:
                active_section.parts.append(text)
                active_section.pages.extend(pages)
            else:
                drafts.append(_fallback_draft(item, text, pages, EvidenceType.paragraph))

    _flush_section(active_section, drafts)
    _apply_title_fallback(drafts)
    return [
        EvidenceItem(
            evidence_id=make_evidence_id(index),
            source_document=source_document,
            **draft,
        )
        for index, draft in enumerate(drafts, start=1)
    ]


def markdown_to_evidence_items(markdown: str, source_document: str) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    current_section: str | None = None
    title_seen = False

    for block in _markdown_blocks(markdown):
        if not _is_meaningful_text(block):
            continue

        if block.startswith("#"):
            heading_text = block.lstrip("#").strip()
            evidence_type = (
                EvidenceType.title
                if block.startswith("# ") and not title_seen
                else EvidenceType.heading
            )
            title_seen = title_seen or evidence_type == EvidenceType.title
            section = None
            if evidence_type == EvidenceType.heading:
                current_section = heading_text
            elif "abstract" in heading_text.lower():
                current_section = heading_text
            text = heading_text
        else:
            evidence_type = infer_evidence_type(block, current_section)
            section = current_section
            text = block.strip()

        chunks = split_long_text(text)
        for chunk in chunks:
            chunk_type = (
                EvidenceType.chunk
                if len(chunks) > 1 and evidence_type == EvidenceType.paragraph
                else evidence_type
            )
            items.append(
                EvidenceItem(
                    evidence_id=make_evidence_id(len(items) + 1),
                    source_document=source_document,
                    type=chunk_type,
                    text=chunk,
                    page=None,
                    section=section,
                    metadata={
                        "backend": "docling",
                        "source": "markdown_fallback",
                    },
                )
            )
    return items


def normalize_label(label: Any) -> str:
    value = getattr(label, "value", label)
    if value is None:
        return ""
    return str(value).strip().lower().replace(" ", "_")


def make_evidence_id(index: int) -> str:
    if index < 1:
        raise ValueError("evidence index must be >= 1")
    return f"ev_{index:06d}"


def infer_evidence_type(
    block: str,
    current_section: str | None = None,
) -> EvidenceType:
    cleaned = block.strip()
    if not cleaned:
        return EvidenceType.unknown
    if cleaned.startswith("#"):
        return EvidenceType.heading
    if current_section and "abstract" in current_section.lower():
        return EvidenceType.abstract
    if cleaned.startswith(("Fig.", "Figure", "TABLE", "Table")):
        return EvidenceType.caption
    if _looks_like_equation(cleaned):
        return EvidenceType.equation
    return EvidenceType.paragraph


def split_long_text(
    text: str,
    max_chars: int = 1200,
    overlap_chars: int = 150,
) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    if overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be smaller than max_chars")

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            split_at = text.rfind(" ", start, end)
            if split_at > start:
                end = split_at
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap_chars, 0)
    return chunks


def _flush_section(
    section: _SectionAccumulator | None,
    drafts: list[dict[str, Any]],
) -> None:
    if section is None:
        return None

    section_text = "\n\n".join(
        [f"{'#' * max(section.heading_level, 1)} {section.heading}", *section.parts]
    ).strip()
    if not _is_meaningful_text(section_text):
        return None

    pages = sorted(set(section.pages))
    metadata = {
        "backend": "docling",
        "source": "docling_native_tree",
        "section_path": section.section_path,
        "heading_level": section.heading_level,
        "page_start": pages[0] if pages else None,
        "page_end": pages[-1] if pages else None,
        "contains_tables": section.table_count > 0,
        "table_count": section.table_count,
        "contains_equations": section.contains_equations,
        "contains_figures": section.contains_figures,
    }

    for text in _split_section_text(section_text):
        part_metadata = dict(metadata)
        if text != section_text:
            part_metadata["split_reason"] = "section_too_large"
        drafts.append(
            _draft(
                evidence_type=section.evidence_type,
                text=text,
                page=pages[0] if pages else None,
                section=section.heading,
                metadata=part_metadata,
            )
        )
    return None


def _split_section_text(text: str) -> list[str]:
    if len(text) <= MAX_SECTION_CHARS:
        return [text]

    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current: list[str] = []
    current_length = 0
    for paragraph in paragraphs:
        added_length = len(paragraph) + (2 if current else 0)
        if current and current_length + added_length > MAX_SECTION_CHARS:
            chunks.append("\n\n".join(current))
            current = [paragraph]
            current_length = len(paragraph)
        else:
            current.append(paragraph)
            current_length += added_length
    if current:
        chunks.append("\n\n".join(current))

    final_chunks: list[str] = []
    for chunk in chunks:
        if len(chunk) <= MAX_SECTION_CHARS:
            final_chunks.append(chunk)
        else:
            final_chunks.extend(
                split_long_text(
                    chunk,
                    max_chars=MAX_SECTION_CHARS,
                    overlap_chars=SECTION_SPLIT_OVERLAP_CHARS,
                )
            )
    return final_chunks


def _draft(
    evidence_type: EvidenceType,
    text: str,
    page: int | None,
    section: str | None,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "type": evidence_type,
        "text": text.strip(),
        "page": page,
        "section": section,
        "metadata": metadata,
    }


def _fallback_draft(
    item: Any,
    text: str,
    pages: list[int],
    evidence_type: EvidenceType,
) -> dict[str, Any]:
    return _draft(
        evidence_type=evidence_type,
        text=text,
        page=min(pages) if pages else None,
        section=None,
        metadata=_base_metadata(item, pages),
    )


def _base_metadata(item: Any, pages: list[int]) -> dict[str, Any]:
    return {
        "backend": "docling",
        "source": "docling_native_tree",
        "docling_label": normalize_label(getattr(item, "label", None)),
        "self_ref": getattr(item, "self_ref", None),
        "page_start": min(pages) if pages else None,
        "page_end": max(pages) if pages else None,
    }


def _item_text(item: Any) -> str:
    text = getattr(item, "text", None)
    if text is None:
        text = getattr(item, "orig", None)
    return str(text).strip() if text is not None else ""


def _caption_text(item: Any, document: Any) -> str:
    caption_text = getattr(item, "caption_text", None)
    if callable(caption_text):
        try:
            caption_text = caption_text(document)
        except TypeError:
            caption_text = caption_text()
    if caption_text:
        return str(caption_text).strip()
    return _item_text(item)


def _table_markdown(item: Any, document: Any) -> str:
    exporter = getattr(item, "export_to_markdown", None)
    if not callable(exporter):
        return _item_text(item)
    try:
        return str(exporter(document)).strip()
    except TypeError:
        return str(exporter()).strip()


def _item_pages(item: Any) -> list[int]:
    pages: list[int] = []
    provenance = getattr(item, "prov", None) or []
    if not isinstance(provenance, (list, tuple)):
        provenance = [provenance]
    for entry in provenance:
        page_no = getattr(entry, "page_no", None)
        if isinstance(page_no, int) and page_no >= 1:
            pages.append(page_no)
    return sorted(set(pages))


def _heading_level(item: Any, iterator_level: int) -> int:
    level = getattr(item, "level", None)
    if isinstance(level, int) and level >= 1:
        return level
    return max(iterator_level, 1)


def _section_evidence_type(heading: str) -> EvidenceType:
    normalized = heading.strip().lower().rstrip(":")
    if "abstract" in normalized:
        return EvidenceType.abstract
    if normalized in {"references", "bibliography"} or normalized.startswith("references"):
        return EvidenceType.reference
    return EvidenceType.section


def _looks_like_inline_abstract(text: str) -> bool:
    normalized = text.strip().lower()
    return normalized.startswith(("abstract:", "abstract.", "abstract -", "abstract —"))


def _is_placeholder(text: str) -> bool:
    cleaned = " ".join(text.strip().lower().split()).rstrip(".")
    return (
        cleaned in {"<!-- image -->", "<!-- formula-not-decoded -->"}
        or cleaned in _NOISY_ISOLATED_TEXT
        or any(cleaned.startswith(prefix) for prefix in _NOISY_TEXT_PREFIXES)
    )


def _apply_title_fallback(drafts: list[dict[str, Any]]) -> None:
    if any(draft["type"] == EvidenceType.title for draft in drafts):
        return

    for draft in drafts:
        heading = draft.get("section") or ""
        if draft["type"] in {EvidenceType.abstract, EvidenceType.reference}:
            return
        if _is_obvious_content_heading(heading):
            return
        if draft["type"] != EvidenceType.section or not _is_title_candidate(heading):
            continue

        if len(_section_body(draft["text"])) > 300:
            return

        draft["type"] = EvidenceType.title
        draft["text"] = heading.strip()
        draft["section"] = None
        draft["metadata"] = {**draft["metadata"], "title_fallback": True}
        return


def _is_obvious_content_heading(text: str) -> bool:
    normalized = " ".join(text.strip().lower().split()).rstrip(".:")
    if normalized in {
        "abstract",
        "bibliography",
        "introduction",
        "references",
    }:
        return True

    words = normalized.split(maxsplit=1)
    if len(words) != 2 or words[1] != "introduction":
        return False
    prefix = words[0].rstrip(".")
    return prefix.isdigit() or prefix in {
        "i",
        "ii",
        "iii",
        "iv",
        "v",
        "vi",
        "vii",
        "viii",
        "ix",
        "x",
    }


def _is_title_candidate(text: str) -> bool:
    cleaned = " ".join(text.strip().split())
    if not cleaned or _is_obvious_content_heading(cleaned) or _is_placeholder(cleaned):
        return False
    return 15 <= len(cleaned) <= 300 and len(cleaned.split()) >= 4


def _section_body(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].lstrip().startswith("#"):
        lines = lines[1:]
    return "\n".join(lines).strip()


def _is_meaningful_text(text: str) -> bool:
    cleaned = text.strip()
    return (
        bool(cleaned)
        and not _is_placeholder(cleaned)
        and any(character.isalnum() for character in cleaned)
    )


def _markdown_blocks(markdown: str) -> list[str]:
    return [block.strip() for block in markdown.split("\n\n") if block.strip()]


def _looks_like_equation(text: str) -> bool:
    if "\n" in text:
        return False
    equation_markers = ("=", "\\(", "\\[", "$")
    return any(marker in text for marker in equation_markers) and any(
        character.isdigit() for character in text
    )
