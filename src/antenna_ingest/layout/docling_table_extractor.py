from __future__ import annotations

from typing import Any, Literal

from antenna_ingest.evidence.schemas import EvidenceStoreDocument, EvidenceType
from antenna_ingest.layout.schemas import TableArtifact


TABLE_EXTRACTOR_NAME = "docling_table_extractor"
TABLE_EXTRACTOR_VERSION = "0.1.0"


def make_table_id(index: int) -> str:
    if index < 1:
        raise ValueError("table index must be >= 1")
    return f"tbl_{index:06d}"


def extract_table_artifacts(
    document: Any,
    source_document: str,
    evidence_document: EvidenceStoreDocument | None = None,
) -> tuple[list[TableArtifact], list[str]]:
    artifacts: list[TableArtifact] = []
    warnings: list[str] = []
    tables = getattr(document, "tables", None) or []

    for index, table in enumerate(tables, start=1):
        table_id = make_table_id(index)
        docling_ref = getattr(table, "self_ref", None)
        pages = _table_pages(table)
        caption = _export_caption(table, document)
        markdown, markdown_warning = _export_markdown(table, document, table_id)
        warnings.extend(markdown_warning)
        rows, row_count, column_count, has_dataframe, dataframe_warning = (
            _export_rows(table, document, table_id)
        )
        warnings.extend(dataframe_warning)
        context_evidence_id, context_link_method = link_table_to_context_evidence(
            page_start=min(pages) if pages else None,
            evidence_document=evidence_document,
        )
        if context_evidence_id is None:
            warnings.append(f"Table {table_id}: no context evidence link found.")
        quality_status, quality_issues, use_for_claim_extraction = (
            assess_table_quality(
                markdown=markdown,
                rows=rows,
                row_count=row_count,
                column_count=column_count,
                caption=caption,
                context_evidence_id=context_evidence_id,
            )
        )

        artifacts.append(
            TableArtifact(
                table_id=table_id,
                source_document=source_document,
                docling_ref=str(docling_ref) if docling_ref is not None else None,
                caption=caption,
                page_start=min(pages) if pages else None,
                page_end=max(pages) if pages else None,
                markdown=markdown,
                rows=rows,
                row_count=row_count,
                column_count=column_count,
                context_evidence_id=context_evidence_id,
                context_link_method=context_link_method,
                quality_status=quality_status,
                quality_issues=quality_issues,
                use_for_claim_extraction=use_for_claim_extraction,
                metadata={
                    "backend": "docling",
                    "self_ref": (
                        str(docling_ref) if docling_ref is not None else None
                    ),
                    "has_dataframe": has_dataframe,
                    "has_markdown": bool(markdown),
                },
            )
        )

    return artifacts, warnings


def assess_table_quality(
    *,
    markdown: str,
    rows: list[dict[str, str | None]],
    row_count: int,
    column_count: int,
    caption: str | None,
    context_evidence_id: str | None,
) -> tuple[Literal["usable", "suspect", "rejected"], list[str], bool]:
    issues: list[str] = []

    if not markdown.strip():
        issues.append("empty_markdown")
    if column_count == 0:
        issues.append("zero_columns")
    if not rows and markdown.strip():
        issues.append("rows_missing")
    if rows and row_count != len(rows):
        issues.append("row_count_mismatch")
    if column_count == 1 and row_count >= 5:
        issues.append("single_column_many_rows")

    cell_values = [value for row in rows for value in row.values()]
    non_empty_values = [
        value.strip()
        for value in cell_values
        if isinstance(value, str) and value.strip()
    ]
    if (
        any(len(value) > 250 for value in non_empty_values)
        or (
            non_empty_values
            and sum(len(value) for value in non_empty_values)
            / len(non_empty_values)
            > 120
        )
    ):
        issues.append("long_prose_cells_detected")

    if cell_values:
        empty_cells = sum(
            value is None or (isinstance(value, str) and not value.strip())
            for value in cell_values
        )
        if empty_cells / len(cell_values) > 0.5:
            issues.append("high_empty_cell_ratio")

    if caption is None and context_evidence_id is None:
        issues.append("weak_context")

    if "empty_markdown" in issues:
        return "rejected", issues, False
    if issues:
        return "suspect", issues, False
    return "usable", issues, True


def link_table_to_context_evidence(
    page_start: int | None,
    evidence_document: EvidenceStoreDocument | None,
) -> tuple[str | None, str | None]:
    if evidence_document is None or page_start is None:
        return None, None

    candidates = []
    for item in evidence_document.items:
        if item.type != EvidenceType.section:
            continue
        item_page_start = item.metadata.get("page_start")
        item_page_end = item.metadata.get("page_end")
        if not isinstance(item_page_start, int) or not isinstance(item_page_end, int):
            continue
        if item_page_start <= page_start <= item_page_end:
            candidates.append(item)

    preferred = [
        item
        for item in candidates
        if item.metadata.get("contains_tables")
        or _positive_int(item.metadata.get("table_count"))
    ]
    if preferred:
        return preferred[0].evidence_id, "page_range_contains_tables"
    if candidates:
        return candidates[0].evidence_id, "page_range"
    return None, None


def _table_pages(table: Any) -> list[int]:
    pages: list[int] = []
    provenance = getattr(table, "prov", None) or []
    if not isinstance(provenance, (list, tuple)):
        provenance = [provenance]
    for entry in provenance:
        page_no = getattr(entry, "page_no", None)
        if isinstance(page_no, int) and page_no >= 1:
            pages.append(page_no)
    return sorted(set(pages))


def _export_caption(table: Any, document: Any) -> str | None:
    exporter = getattr(table, "caption_text", None)
    if not callable(exporter):
        return None
    try:
        caption = exporter(doc=document)
    except TypeError:
        try:
            caption = exporter()
        except Exception:
            return None
    except Exception:
        return None
    cleaned = str(caption).strip() if caption is not None else ""
    return cleaned or None


def _export_markdown(
    table: Any,
    document: Any,
    table_id: str,
) -> tuple[str, list[str]]:
    exporter = getattr(table, "export_to_markdown", None)
    warnings: list[str] = []
    if not callable(exporter):
        warnings.append(f"Table {table_id}: markdown export failed.")
        warnings.append(f"Table {table_id}: markdown is empty.")
        return "", warnings

    try:
        markdown = exporter(doc=document)
    except TypeError:
        try:
            markdown = exporter()
        except Exception:
            warnings.append(f"Table {table_id}: markdown export failed.")
            markdown = ""
    except Exception:
        warnings.append(f"Table {table_id}: markdown export failed.")
        markdown = ""

    cleaned = str(markdown).strip() if markdown is not None else ""
    if not cleaned:
        warnings.append(f"Table {table_id}: markdown is empty.")
    return cleaned, warnings


def _export_rows(
    table: Any,
    document: Any,
    table_id: str,
) -> tuple[list[dict[str, str | None]], int, int, bool, list[str]]:
    exporter = getattr(table, "export_to_dataframe", None)
    if not callable(exporter):
        return [], 0, 0, False, [
            f"Table {table_id}: dataframe export failed."
        ]

    try:
        dataframe = exporter(doc=document)
    except TypeError:
        try:
            dataframe = exporter()
        except Exception:
            return [], 0, 0, False, [
                f"Table {table_id}: dataframe export failed."
            ]
    except Exception:
        return [], 0, 0, False, [
            f"Table {table_id}: dataframe export failed."
        ]

    try:
        row_count, column_count = dataframe.shape
        records = dataframe.to_dict(orient="records")
        rows = [
            {
                str(key): None if value is None else str(value)
                for key, value in record.items()
            }
            for record in records
        ]
    except Exception:
        return [], 0, 0, False, [
            f"Table {table_id}: dataframe export failed."
        ]
    return rows, int(row_count), int(column_count), True, []


def _positive_int(value: Any) -> bool:
    try:
        return int(value) > 0
    except (TypeError, ValueError):
        return False
