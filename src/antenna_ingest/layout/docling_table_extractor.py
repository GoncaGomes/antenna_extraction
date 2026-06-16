from __future__ import annotations

import re
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
                    "quality_checked": True,
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
    reject_score = 0
    suspect_score = 0

    headers = _header_values(rows)
    values = _cell_values(rows)
    empty_ratio = _empty_cell_ratio(rows)
    repeated_count = _count_repeated_adjacent_token_values([*headers, *values])
    long_text_count = _count_long_text_cells(values)
    prose_header_count = _count_prose_like_headers(headers)
    multi_value_count = _count_multi_value_cells(values)

    if not markdown.strip():
        issues.append("empty_markdown")
        reject_score += 3
    if column_count == 0:
        issues.append("zero_columns")
        if not markdown.strip():
            reject_score += 2
        else:
            suspect_score += 1
    if not rows and markdown.strip():
        issues.append("rows_missing")
        suspect_score += 1
    if rows and row_count != len(rows):
        issues.append("row_count_mismatch")
        suspect_score += 1
    if column_count == 1 and row_count >= 4:
        issues.append("single_column_many_rows")
        suspect_score += 2
    if long_text_count >= 1:
        issues.append("long_text_cells_detected")
        suspect_score += 2
    if long_text_count >= 2:
        issues.append("severe_text_leakage")
        reject_score += 2
    if values and long_text_count / len(values) >= 0.20:
        issues.append("severe_text_leakage")
        reject_score += 2
    if rows and empty_ratio > 0.50:
        issues.append("high_empty_cell_ratio")
        suspect_score += 1

    if caption is None and context_evidence_id is None:
        issues.append("weak_context")
        suspect_score += 1
    if repeated_count >= 1:
        issues.append("repeated_adjacent_tokens_detected")
        suspect_score += 1
    if repeated_count >= 3:
        reject_score += 1
    if _caption_duplicated_in_markdown(caption, markdown):
        issues.append("caption_duplicated_in_markdown")
        suspect_score += 2
    if prose_header_count >= 1:
        issues.append("prose_like_headers_detected")
        suspect_score += 2
    if prose_header_count >= 3:
        reject_score += 1
    if multi_value_count >= 2:
        issues.append("multi_value_cells_detected")
        suspect_score += 1
    if multi_value_count >= 4:
        reject_score += 1
    if _numeric_header_drift_detected(headers):
        issues.append("numeric_header_drift_detected")
        suspect_score += 2
    if _header_cell_overlap_detected(rows):
        issues.append("header_cell_overlap_detected")
        suspect_score += 2

    if reject_score >= 3:
        quality_status = "rejected"
    elif reject_score > 0 and suspect_score >= 2:
        quality_status = "rejected"
    elif suspect_score >= 4:
        quality_status = "rejected"
    elif suspect_score > 0 or reject_score > 0:
        quality_status = "suspect"
    else:
        quality_status = "usable"

    return (
        quality_status,
        sorted(set(issues)),
        quality_status == "usable",
    )


def _normalize_space(text: str) -> str:
    return " ".join(text.split()).strip()


def _tokenize_for_repetition(text: str) -> list[str]:
    return [
        token.casefold()
        for token in re.findall(
            r"[A-Za-zΑ-ωΩµμ]+|\d+(?:\.\d+)?",
            text,
        )
    ]


def _cell_values(rows: list[dict[str, str | None]]) -> list[str]:
    return [
        value.strip()
        for row in rows
        for value in row.values()
        if isinstance(value, str) and value.strip()
    ]


def _all_cell_values_including_empty(
    rows: list[dict[str, str | None]],
) -> list[str | None]:
    return [value for row in rows for value in row.values()]


def _header_values(rows: list[dict[str, str | None]]) -> list[str]:
    if not rows:
        return []

    keys = [_normalize_space(str(key)) for key in rows[0]]
    keys = [key for key in keys if key]
    numeric_keys = sum(key.isdigit() for key in keys)
    if keys and numeric_keys / len(keys) > 0.5:
        first_row_values = [
            _normalize_space(value)
            for value in rows[0].values()
            if isinstance(value, str) and _normalize_space(value)
        ]
        return first_row_values
    return keys


def _empty_cell_ratio(rows: list[dict[str, str | None]]) -> float:
    values = _all_cell_values_including_empty(rows)
    if not values:
        return 0.0
    empty_count = sum(
        value is None or (isinstance(value, str) and not value.strip())
        for value in values
    )
    return empty_count / len(values)


def _has_repeated_adjacent_tokens(text: str) -> bool:
    tokens = _tokenize_for_repetition(text)
    if any(left == right for left, right in zip(tokens, tokens[1:])):
        return True
    return any(
        tokens[index : index + 2] == tokens[index + 2 : index + 4]
        for index in range(len(tokens) - 3)
    )


def _count_repeated_adjacent_token_values(values: list[str]) -> int:
    return sum(_has_repeated_adjacent_tokens(value) for value in values)


def _count_long_text_cells(values: list[str]) -> int:
    return sum(
        len(value) > 220
        or (
            len(value) > 120
            and (
                any(punctuation in value for punctuation in ".,;")
                or len(value.split()) >= 8
            )
        )
        for value in values
    )


def _count_prose_like_headers(headers: list[str]) -> int:
    stopwords = {
        "the",
        "and",
        "of",
        "between",
        "with",
        "from",
        "to",
        "for",
        "in",
        "on",
        "using",
        "where",
        "which",
    }
    count = 0
    for header in headers:
        words = _tokenize_for_repetition(header)
        stopword_count = sum(word in stopwords for word in words)
        if len(header) > 80 or len(header.split()) > 6 or stopword_count >= 2:
            count += 1
    return count


def _count_multi_value_cells(values: list[str]) -> int:
    count = 0
    for value in values:
        numeric_tokens = re.findall(r"\d+(?:\.\d+)?", value)
        repeated_numeric = any(
            left == right
            for left, right in zip(numeric_tokens, numeric_tokens[1:])
        )
        if len(numeric_tokens) >= 4 or repeated_numeric:
            count += 1
    return count


def _caption_duplicated_in_markdown(
    caption: str | None,
    markdown: str,
) -> bool:
    if caption is None:
        return False
    caption_prefix = _normalize_space(caption).casefold()[:80]
    normalized_markdown = _normalize_space(markdown).casefold()
    return bool(caption_prefix) and normalized_markdown.count(caption_prefix) > 1


def _numeric_header_drift_detected(headers: list[str]) -> bool:
    if not headers:
        return False
    drifted = 0
    for header in headers:
        has_alpha = any(character.isalpha() for character in header)
        numeric_tokens = re.findall(r"\d+(?:\.\d+)?", header)
        if has_alpha and len(numeric_tokens) > 1:
            drifted += 1
    return drifted / len(headers) >= 0.5


def _header_cell_overlap_detected(
    rows: list[dict[str, str | None]],
) -> bool:
    if not rows:
        return False
    first_row_values = [
        value
        for value in rows[0].values()
        if isinstance(value, str) and value.strip()
    ]
    if any(_has_repeated_adjacent_tokens(value) for value in first_row_values):
        return True

    generic_labels = {
        "average",
        "description",
        "label",
        "labels",
        "maximum",
        "mean",
        "measurement",
        "minimum",
        "parameter",
        "quantity",
        "unit",
        "units",
        "value",
        "values",
    }
    header_tokens = {
        token
        for header in rows[0]
        for token in _tokenize_for_repetition(str(header))
        if token in generic_labels
    }
    value_tokens = {
        token
        for value in first_row_values
        for token in _tokenize_for_repetition(value)
        if token in generic_labels
    }
    return bool(header_tokens & value_tokens)


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
