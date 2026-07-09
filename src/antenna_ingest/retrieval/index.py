from __future__ import annotations

import json
import math
from pathlib import Path

from pydantic import Field

from antenna_ingest.evidence.blocks import EvidenceBlock
from antenna_ingest.evidence.tables import ExtractedTable, TablesDocument
from antenna_ingest.orchestration.runs import sha256_file
from antenna_ingest.orchestration.schemas import (
    ArtifactReference,
    PhaseStatus,
    RunManifest,
    StrictModel,
)
from antenna_ingest.utils.json_io import read_json, write_json


EVIDENCE_INDEX_PHASE = "evidence_indexing"
EVIDENCE_BLOCKS_PATH = "parsed/evidence_blocks.jsonl"
TABLES_PATH = "parsed/tables.json"
EVIDENCE_INDEX_PATH = "retrieval/evidence_index.jsonl"
EVIDENCE_INDEX_REPORT_PATH = "retrieval/evidence_index_report.json"

STOPWORDS = {
    "the",
    "a",
    "an",
    "of",
    "and",
    "or",
    "in",
    "on",
    "with",
    "for",
    "to",
    "from",
    "by",
    "is",
    "are",
    "was",
    "were",
    "this",
    "that",
    "proposed",
    "antenna",
}
UNIT_ALIASES = {
    "mm": "mm",
    "cm": "cm",
    "m": "m",
    "ghz": "GHz",
    "mhz": "MHz",
    "hz": "Hz",
    "db": "dB",
    "dbi": "dBi",
    "ohm": "ohm",
    "ohms": "ohm",
    "omega": "\u03a9",
    "\\omega": "\u03a9",
    "\u03c9": "\u03a9",
    "pf": "pF",
    "nh": "nH",
}
SURROUNDING_PUNCTUATION = ".,;:!?()[]{}<>\"'`*#$"


class EvidenceIndexItem(StrictModel):
    evidence_id: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    page: int = Field(ge=1)
    kind: str = Field(min_length=1)
    order: int = Field(ge=0)
    text: str = Field(min_length=1)
    section: str | None = None
    caption: str | None = None
    tokens: list[str] = Field(default_factory=list)
    key_tokens: list[str] = Field(default_factory=list)
    numbers: list[str] = Field(default_factory=list)
    units: list[str] = Field(default_factory=list)
    previous_id: str | None = None
    next_id: str | None = None
    source_artifact: str = Field(min_length=1)


class EvidenceIndexReport(StrictModel):
    source_blocks: str = Field(min_length=1)
    source_tables: str = Field(min_length=1)
    output_index: str = Field(min_length=1)
    item_count: int = Field(ge=0)
    block_count: int = Field(ge=0)
    table_count: int = Field(ge=0)
    page_count: int = Field(ge=1)
    warnings: list[str] = Field(default_factory=list)


def build_evidence_index_from_run(
    run_dir: Path,
    force: bool = False,
) -> EvidenceIndexReport:
    run_dir = Path(run_dir).resolve()
    manifest_path = run_dir / "manifest.json"
    manifest = RunManifest.model_validate(read_json(manifest_path))
    refuse_existing_index_outputs(run_dir, force)

    manifest.phase_status[EVIDENCE_INDEX_PHASE] = PhaseStatus.RUNNING
    write_json(manifest_path, manifest.model_dump(mode="json"))

    try:
        blocks = [
            EvidenceBlock.model_validate(item)
            for item in read_jsonl(run_dir / EVIDENCE_BLOCKS_PATH)
        ]
        tables_document = TablesDocument.model_validate(
            read_json(run_dir / TABLES_PATH)
        )
        items = build_index_items(blocks, tables_document.tables)
        if not items:
            raise ValueError("no evidence blocks or tables were available to index")

        write_jsonl(run_dir / EVIDENCE_INDEX_PATH, items)
        report = EvidenceIndexReport(
            source_blocks=EVIDENCE_BLOCKS_PATH,
            source_tables=TABLES_PATH,
            output_index=EVIDENCE_INDEX_PATH,
            item_count=len(items),
            block_count=len(blocks),
            table_count=len(tables_document.tables),
            page_count=len({item.page for item in items}),
            warnings=[],
        )
        write_json(
            run_dir / EVIDENCE_INDEX_REPORT_PATH,
            report.model_dump(mode="json"),
        )

        manifest = RunManifest.model_validate(read_json(manifest_path))
        manifest.phase_status[EVIDENCE_INDEX_PHASE] = PhaseStatus.COMPLETED
        replace_evidence_index_artifacts(manifest, run_dir)
        write_json(manifest_path, manifest.model_dump(mode="json"))
        return report
    except Exception:
        failed_manifest = RunManifest.model_validate(read_json(manifest_path))
        failed_manifest.phase_status[EVIDENCE_INDEX_PHASE] = PhaseStatus.FAILED
        write_json(manifest_path, failed_manifest.model_dump(mode="json"))
        raise


def build_index_items(
    blocks: list[EvidenceBlock],
    tables: list[ExtractedTable],
) -> list[EvidenceIndexItem]:
    items: list[EvidenceIndexItem] = []
    indexed_blocks = [
        block for block in blocks if not is_raw_html_table_block(block)
    ]
    block_evidence_ids = [f"block_{block.block_id}" for block in indexed_blocks]
    current_section: str | None = None

    for index, block in enumerate(indexed_blocks):
        section = current_section
        if block.kind == "heading":
            current_section = block.text
        items.append(
            EvidenceIndexItem(
                evidence_id=block_evidence_ids[index],
                source_type="block",
                source_id=block.block_id,
                page=block.page,
                kind=block.kind,
                order=len(items),
                text=block.text,
                section=section,
                tokens=tokenize_text(block.text),
                key_tokens=extract_key_tokens(block.text),
                numbers=extract_numbers_from_tokens(tokenize_text(block.text)),
                units=extract_units_from_tokens(tokenize_text(block.text)),
                previous_id=block_evidence_ids[index - 1] if index > 0 else None,
                next_id=(
                    block_evidence_ids[index + 1]
                    if index + 1 < len(indexed_blocks)
                    else None
                ),
                source_artifact=EVIDENCE_BLOCKS_PATH,
            )
        )

    for table in tables:
        text = render_table_as_pipe_markdown(table)
        metadata_text = "\n".join((text, table.raw_markdown))
        tokens = tokenize_text(metadata_text)
        units = _unique_preserving_order(
            [*table.units, *extract_units_from_tokens(tokens)]
        )
        items.append(
            EvidenceIndexItem(
                evidence_id=table.table_id,
                source_type="table",
                source_id=table.table_id,
                page=table.page,
                kind="table",
                order=len(items),
                text=text,
                caption=table.caption,
                tokens=tokens,
                key_tokens=extract_key_tokens(
                    metadata_text,
                    table_headers=table.headers,
                    caption=table.caption,
                ),
                numbers=extract_numbers_from_tokens(tokens),
                units=units,
                source_artifact=TABLES_PATH,
            )
        )
    return items


def is_raw_html_table_block(block: EvidenceBlock) -> bool:
    return block.kind == "table" and "<table" in block.text.lower()


def render_table_as_pipe_markdown(table: ExtractedTable) -> str:
    column_count = max(
        [len(table.headers), *(len(row) for row in table.rows), 1]
    )
    headers = [_clean_table_cell(header) for header in table.headers]
    if not headers:
        headers = [f"Column {index}" for index in range(1, column_count + 1)]
    elif len(headers) < column_count:
        headers.extend(
            f"Column {index}" for index in range(len(headers) + 1, column_count + 1)
        )

    lines = []
    if table.caption:
        lines.extend((_clean_table_cell(table.caption), ""))
    lines.append(_pipe_row(headers[:column_count]))
    lines.append(_separator_row(column_count))
    for row in table.rows:
        cells = [_clean_table_cell(cell) for cell in row]
        cells.extend([""] * (column_count - len(cells)))
        lines.append(_pipe_row(cells[:column_count]))
    return "\n".join(lines)


def _pipe_row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _separator_row(column_count: int) -> str:
    return "|" + "|".join("---" for _ in range(column_count)) + "|"


def _clean_table_cell(value: str) -> str:
    cleaned = " ".join(value.split()).strip()
    if len(cleaned) >= 2 and cleaned.startswith("$") and cleaned.endswith("$"):
        cleaned = cleaned[1:-1].strip()
    return cleaned.replace("|", r"\|")


def tokenize_text(text: str) -> list[str]:
    normalized = text.replace("&nbsp;", " ").replace("\u00a0", " ")
    for separator in ("=", ":", "|", "\n", "\r", "\t"):
        normalized = normalized.replace(separator, " ")

    tokens = []
    for raw_token in normalized.split():
        token = _clean_token(raw_token)
        if token:
            tokens.append(token)
            compact_alias = _compact_token_alias(token)
            if compact_alias != token:
                tokens.append(compact_alias)
    return _unique_preserving_order(tokens)


def extract_key_tokens(
    text: str,
    table_headers: list[str] | None = None,
    caption: str | None = None,
) -> list[str]:
    tokens = tokenize_text(text)
    numbers = set(extract_numbers_from_tokens(tokens))
    units = {unit.lower() for unit in extract_units_from_tokens(tokens)}
    key_tokens: list[str] = []

    for header in table_headers or []:
        key_tokens.extend(tokenize_text(header))
    key_tokens.extend(
        token
        for token in tokenize_text(caption or "")
        if token.lower() not in STOPWORDS
    )

    for index, token in enumerate(tokens):
        lowered = token.lower()
        near_number_or_unit = any(
            _number_value(nearby) in numbers or nearby.lower() in units
            for nearby in tokens[max(0, index - 2) : index + 3]
        )
        if lowered in STOPWORDS or _number_value(token) is not None:
            continue
        if len(token) == 1 and not near_number_or_unit:
            continue
        if near_number_or_unit or (len(token) <= 16 and _contains_alphanumeric(token)):
            key_tokens.append(token)

    for separator in ("=", ":", "|"):
        fragments = text.replace(separator, f" {separator} ").split()
        for index, fragment in enumerate(fragments):
            if fragment != separator:
                continue
            for neighbour in fragments[max(0, index - 1) : index + 2]:
                token = _clean_token(neighbour)
                if token and token != separator and token.lower() not in STOPWORDS:
                    key_tokens.append(token)

    return _unique_preserving_order(key_tokens)


def extract_numbers_from_tokens(tokens: list[str]) -> list[str]:
    return _unique_preserving_order(
        value for token in tokens if (value := _number_value(token)) is not None
    )


def extract_units_from_tokens(tokens: list[str]) -> list[str]:
    units = []
    for token in tokens:
        normalized = token.replace("\\Omega", "\u03a9").lower()
        unit = UNIT_ALIASES.get(normalized)
        if unit:
            units.append(unit)
    return _unique_preserving_order(units)


def read_jsonl(path: Path) -> list[dict]:
    items = []
    with Path(path).open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            item = json.loads(line)
            if not isinstance(item, dict):
                raise ValueError(f"JSONL line {line_number} must be an object")
            items.append(item)
    return items


def write_jsonl(path: Path, items: list[EvidenceIndexItem]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for item in items:
            json.dump(item.model_dump(mode="json"), file, ensure_ascii=False)
            file.write("\n")


def refuse_existing_index_outputs(run_dir: Path, force: bool) -> None:
    paths = [
        Path(run_dir) / EVIDENCE_INDEX_PATH,
        Path(run_dir) / EVIDENCE_INDEX_REPORT_PATH,
    ]
    existing = [path for path in paths if path.exists()]
    if existing and not force:
        raise FileExistsError(f"evidence index output already exists: {existing[0]}")
    for path in existing:
        path.unlink()


def replace_evidence_index_artifacts(
    manifest: RunManifest,
    run_dir: Path,
) -> None:
    artifact_names = {"evidence_index", "evidence_index_report"}
    manifest.artifacts = [
        artifact
        for artifact in manifest.artifacts
        if artifact.name not in artifact_names
    ]
    for name, relative_path in (
        ("evidence_index", EVIDENCE_INDEX_PATH),
        ("evidence_index_report", EVIDENCE_INDEX_REPORT_PATH),
    ):
        manifest.add_artifact(
            ArtifactReference(
                name=name,
                relative_path=relative_path,
                producing_phase=EVIDENCE_INDEX_PHASE,
                checksum=sha256_file(Path(run_dir) / relative_path),
            )
        )


def _clean_token(token: str) -> str:
    return token.strip(SURROUNDING_PUNCTUATION)


def _number_value(token: str) -> str | None:
    candidate = _clean_token(token)
    if candidate.count(",") == 1 and "." not in candidate:
        candidate = candidate.replace(",", ".")
    try:
        number = float(candidate)
    except ValueError:
        return None
    if not math.isfinite(number):
        return None
    return candidate


def _contains_alphanumeric(token: str) -> bool:
    return any(character.isalnum() for character in token)


def _compact_token_alias(token: str) -> str:
    return token.replace("_", "").replace("{", "").replace("}", "")


def _unique_preserving_order(values) -> list[str]:
    unique = []
    seen = set()
    for value in values:
        key = value.lower()
        if key not in seen:
            seen.add(key)
            unique.append(value)
    return unique
