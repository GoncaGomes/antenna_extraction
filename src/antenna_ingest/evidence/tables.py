from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from pydantic import Field

from antenna_ingest.evidence.blocks import split_markdown_pages
from antenna_ingest.orchestration.runs import sha256_file
from antenna_ingest.orchestration.schemas import (
    ArtifactReference,
    PhaseStatus,
    RunManifest,
    StrictModel,
)
from antenna_ingest.utils.json_io import read_json, write_json


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
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.lower() == "tr":
            self._current_row = []
        elif tag.lower() in {"th", "td"} and self._current_row is not None:
            self._current_cell = []

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"th", "td"} and self._current_cell is not None:
            if self._current_row is not None:
                self._current_row.append(clean_text("".join(self._current_cell)))
            self._current_cell = None
        elif lowered == "tr" and self._current_row is not None:
            if self._current_row:
                self.rows.append(self._current_row)
            self._current_row = None


def extract_tables_from_run(
    run_dir: Path,
    force: bool = False,
) -> TablesReport:
    run_dir = Path(run_dir).resolve()
    manifest_path = run_dir / "manifest.json"
    manifest = RunManifest.model_validate(read_json(manifest_path))
    refuse_existing_table_outputs(run_dir, force)

    manifest.phase_status[TABLE_EXTRACTION_PHASE] = PhaseStatus.RUNNING
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
                caption = find_nearby_caption(page_text, match.start())
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

        manifest = RunManifest.model_validate(read_json(manifest_path))
        manifest.phase_status[TABLE_EXTRACTION_PHASE] = PhaseStatus.COMPLETED
        replace_table_artifacts(manifest, run_dir)
        write_json(manifest_path, manifest.model_dump(mode="json"))
        return report
    except Exception:
        failed_manifest = RunManifest.model_validate(read_json(manifest_path))
        failed_manifest.phase_status[TABLE_EXTRACTION_PHASE] = PhaseStatus.FAILED
        write_json(manifest_path, failed_manifest.model_dump(mode="json"))
        raise


def find_nearby_caption(page_text: str, table_start: int) -> str | None:
    before = page_text[:table_start]
    lines = [line.strip() for line in before.splitlines() if line.strip()]
    for line in reversed(lines[-8:]):
        lowered = line.lower()
        if lowered.startswith(("table", "tab.", "**table")):
            return clean_text(line)
    return None


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
