from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from pydantic import Field

from antenna_ingest.evidence.blocks import split_markdown_pages
from antenna_ingest.orchestration.phases import complete_phase, fail_phase, start_phase
from antenna_ingest.orchestration.runs import load_run_manifest, sha256_file
from antenna_ingest.orchestration.schemas import (
    ArtifactReference,
    RunManifest,
    StrictModel,
)
from antenna_ingest.utils.json_io import write_json


TABLE_EXTRACTION_PHASE = "table_extraction"
TABLES_PATH = "parsed/tables.json"
TABLES_REPORT_PATH = "parsed/tables_report.json"
SOURCE_MARKDOWN_PATH = "parsed/document.nuextract.md"
HTML_TABLE_RE = re.compile(
    r"<table\b.*?</table>",
    flags=re.IGNORECASE | re.DOTALL,
)
KNOWN_UNITS = ("mm", "cm", "m", "GHz", "MHz", "Hz", "dB", "dBi", "\u03a9", "ohm")
UNIT_RE = re.compile(
    r"(?<![A-Za-z])(" + "|".join(re.escape(unit) for unit in KNOWN_UNITS) + r")(?![A-Za-z])",
    flags=re.IGNORECASE,
)


class ExtractedTable(StrictModel):
    table_id: str = Field(min_length=1)
    page: int = Field(ge=1)
    caption: str | None = None
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    units: list[str] = Field(default_factory=list)
    raw_markdown: str = Field(min_length=1)
    source: str = Field(min_length=1)


class TablesDocument(StrictModel):
    source_markdown: str = Field(min_length=1)
    tables: list[ExtractedTable] = Field(default_factory=list)


class TablesReport(StrictModel):
    source_markdown: str = Field(min_length=1)
    output_tables: str = Field(min_length=1)
    table_count: int = Field(ge=0)
    page_count: int = Field(ge=1)
    warnings: list[str] = Field(default_factory=list)


class SimpleHTMLTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self.caption_parts: list[str] = []
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None
        self._in_caption = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        lowered = tag.lower()
        if lowered == "caption":
            self._in_caption = True
        elif lowered == "br" and self._in_caption:
            self.caption_parts.append(" ")
        elif lowered == "tr":
            self._current_row = []
        elif lowered in {"th", "td"} and self._current_row is not None:
            self._current_cell = []

    def handle_data(self, data: str) -> None:
        if self._in_caption:
            self.caption_parts.append(data)
        elif self._current_cell is not None:
            self._current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered == "caption":
            self._in_caption = False
        elif lowered in {"th", "td"} and self._current_cell is not None:
            if self._current_row is not None:
                self._current_row.append(clean_text("".join(self._current_cell)))
            self._current_cell = None
        elif lowered == "tr" and self._current_row is not None:
            if self._current_row:
                self.rows.append(self._current_row)
            self._current_row = None

    @property
    def caption(self) -> str | None:
        caption = clean_text(" ".join(self.caption_parts))
        return caption or None


def extract_tables_from_run(
    run_dir: Path,
    force: bool = False,
) -> TablesReport:
    run_dir = Path(run_dir).resolve()
    manifest_path = run_dir / "manifest.json"
    manifest = load_run_manifest(manifest_path)
    refuse_existing_table_outputs(run_dir, force)

    start_phase(manifest, TABLE_EXTRACTION_PHASE)
    write_json(manifest_path, manifest.model_dump(mode="json"))

    try:
        markdown = (run_dir / SOURCE_MARKDOWN_PATH).read_text(encoding="utf-8")
        pages = split_markdown_pages(markdown)
        if not pages:
            raise ValueError("source Markdown contains no page markers")

        tables = []
        for page, page_text in pages:
            for match in HTML_TABLE_RE.finditer(page_text):
                raw_table = match.group(0).strip()
                parser = SimpleHTMLTableParser()
                parser.feed(raw_table)
                headers = parser.rows[0] if "<th" in raw_table.lower() and parser.rows else []
                rows = parser.rows[1:] if headers else parser.rows
                caption = parser.caption or find_nearby_caption(
                    page_text,
                    match.start(),
                )
                tables.append(
                    ExtractedTable(
                        table_id=f"table_{len(tables) + 1:03d}",
                        page=page,
                        caption=caption,
                        headers=headers,
                        rows=rows,
                        units=detect_units(caption, headers, rows, raw_table),
                        raw_markdown=raw_table,
                        source=SOURCE_MARKDOWN_PATH,
                    )
                )

        document = TablesDocument(
            source_markdown=SOURCE_MARKDOWN_PATH,
            tables=tables,
        )
        write_json(run_dir / TABLES_PATH, document.model_dump(mode="json"))
        report = TablesReport(
            source_markdown=SOURCE_MARKDOWN_PATH,
            output_tables=TABLES_PATH,
            table_count=len(tables),
            page_count=len(pages),
            warnings=[],
        )
        write_json(run_dir / TABLES_REPORT_PATH, report.model_dump(mode="json"))

        manifest = load_run_manifest(manifest_path)
        complete_phase(manifest, TABLE_EXTRACTION_PHASE)
        replace_table_artifacts(manifest, run_dir)
        write_json(manifest_path, manifest.model_dump(mode="json"))
        return report
    except Exception:
        failed_manifest = load_run_manifest(manifest_path)
        fail_phase(failed_manifest, TABLE_EXTRACTION_PHASE, None)
        write_json(manifest_path, failed_manifest.model_dump(mode="json"))
        raise


def find_nearby_caption(page_text: str, table_start: int) -> str | None:
    before = page_text[:table_start]
    lines = [line.strip() for line in before.splitlines() if line.strip()]
    nearby_lines = lines[-12:]
    table_line_index = None
    for index in range(len(nearby_lines) - 1, -1, -1):
        if is_table_caption_start(nearby_lines[index]):
            table_line_index = index
            break
    if table_line_index is None:
        return None

    caption_lines = [nearby_lines[table_line_index]]
    for line in nearby_lines[table_line_index + 1 :]:
        if is_caption_continuation(line):
            caption_lines.append(line)
        else:
            break
    return clean_text(" ".join(caption_lines))


def is_table_caption_start(line: str) -> bool:
    return line.lower().startswith(("table", "tab.", "**table"))


def is_caption_continuation(line: str) -> bool:
    cleaned = clean_text(line)
    if not cleaned or len(cleaned) > 100:
        return False
    if cleaned.lower().startswith(("<table", "figure", "fig.")):
        return False
    if cleaned.endswith(".") and len(cleaned.split()) > 6:
        return False
    letters = [character for character in cleaned if character.isalpha()]
    if letters:
        uppercase_ratio = sum(1 for character in letters if character.isupper()) / len(
            letters
        )
        if uppercase_ratio >= 0.7:
            return True
    words = [
        word.strip("()[]{}:;,.")
        for word in cleaned.split()
        if any(character.isalpha() for character in word)
    ]
    if not words or len(words) > 10:
        return False
    small_words = {"a", "an", "and", "by", "for", "in", "of", "on", "the", "to"}
    return all(
        word.lower() in small_words or word[:1].isupper()
        for word in words
    )


def detect_units(
    caption: str | None,
    headers: list[str],
    rows: list[list[str]],
    raw_table: str,
) -> list[str]:
    text = "\n".join(
        [caption or "", *headers, *(cell for row in rows for cell in row), raw_table]
    )
    canonical_units = {unit.lower(): unit for unit in KNOWN_UNITS}
    units = []
    for match in UNIT_RE.finditer(text):
        unit = canonical_units[match.group(0).lower()]
        if unit not in units:
            units.append(unit)
    return units


def clean_text(text: str) -> str:
    return " ".join(text.split()).strip()


def refuse_existing_table_outputs(run_dir: Path, force: bool) -> None:
    paths = [Path(run_dir) / TABLES_PATH, Path(run_dir) / TABLES_REPORT_PATH]
    existing = [path for path in paths if path.exists()]
    if existing and not force:
        raise FileExistsError(f"table output already exists: {existing[0]}")
    for path in existing:
        path.unlink()


def replace_table_artifacts(manifest: RunManifest, run_dir: Path) -> None:
    artifact_names = {"tables", "tables_report"}
    manifest.artifacts = [
        artifact
        for artifact in manifest.artifacts
        if artifact.name not in artifact_names
    ]
    for name, relative_path in (
        ("tables", TABLES_PATH),
        ("tables_report", TABLES_REPORT_PATH),
    ):
        manifest.add_artifact(
            ArtifactReference(
                name=name,
                relative_path=relative_path,
                producing_phase=TABLE_EXTRACTION_PHASE,
                checksum=sha256_file(Path(run_dir) / relative_path),
            )
        )
