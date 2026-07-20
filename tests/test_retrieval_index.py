from __future__ import annotations

import json
from pathlib import Path

import pytest

from antenna_ingest.evidence.tables import ExtractedTable
from antenna_ingest.orchestration.schemas import PhaseStatus, RunManifest
from antenna_ingest.retrieval.index import (
    EVIDENCE_INDEX_PATH,
    EVIDENCE_INDEX_REPORT_PATH,
    build_evidence_index_from_run,
    read_jsonl,
    render_table_as_pipe_markdown,
    tokenize_text,
)
from antenna_ingest.utils.json_io import read_json, write_json


def test_build_index_from_blocks_and_tables(tmp_path) -> None:
    run_dir = make_retrieval_run(tmp_path)

    report = build_evidence_index_from_run(run_dir)

    assert (run_dir / EVIDENCE_INDEX_PATH).exists()
    assert (run_dir / EVIDENCE_INDEX_REPORT_PATH).exists()
    assert report.item_count == 4
    items = read_jsonl(run_dir / EVIDENCE_INDEX_PATH)
    assert len(items) == 4
    assert all("<table" not in item["text"].lower() for item in items)
    assert "block_page_2_block_004" not in {
        item["evidence_id"] for item in items
    }

    heading, paragraph, figure, table = items
    assert heading["next_id"] == paragraph["evidence_id"]
    assert paragraph["previous_id"] == heading["evidence_id"]
    assert paragraph["next_id"] == figure["evidence_id"]
    assert figure["previous_id"] == paragraph["evidence_id"]
    assert paragraph["section"] == "Antenna Design"
    assert table["evidence_id"] == "table_001"
    assert table["source_type"] == "table"
    assert table["text"].startswith("TABLE I ANTENNA PARAMETERS\n\n| S1 |")
    assert "| 92 | 96 | 45 | 68 | 76 |" in table["text"]
    assert {"S1", "S2", "P1", "P2", "L1"} <= set(table["key_tokens"])
    assert {"92", "96", "45", "68", "76"} <= set(table["numbers"])
    assert "mm" in table["units"]

    manifest = RunManifest.model_validate(read_json(run_dir / "manifest.json"))
    assert manifest.phases["evidence_indexing"].status == PhaseStatus.COMPLETED
    artifact_names = {artifact.name for artifact in manifest.artifacts}
    assert {"evidence_index", "evidence_index_report"} <= artifact_names


def test_build_index_force_controls_overwrite(tmp_path) -> None:
    run_dir = make_retrieval_run(tmp_path)
    build_evidence_index_from_run(run_dir)

    with pytest.raises(FileExistsError):
        build_evidence_index_from_run(run_dir)

    (run_dir / EVIDENCE_INDEX_PATH).write_text("stale\n", encoding="utf-8")
    report = build_evidence_index_from_run(run_dir, force=True)

    assert report.item_count == 4
    assert "stale" not in (run_dir / EVIDENCE_INDEX_PATH).read_text(
        encoding="utf-8"
    )


def test_tokenizer_preserves_and_compacts_decorated_tokens() -> None:
    tokens = tokenize_text("$S_1$ alpha_gap")

    assert {"S_1", "S1", "alpha_gap", "alphagap"} <= set(tokens)


def test_render_table_as_pipe_markdown_handles_generic_table_shapes() -> None:
    explicit_headers = table_fixture(
        table_id="table_headers",
        caption="Parameter Table",
        headers=["Name", "Value"],
        rows=[["Length", "31.43 mm"], ["Width", "40.57 mm"]],
    )
    no_headers = table_fixture(
        table_id="table_no_headers",
        rows=[["Length", "31.43 mm"], ["Width", "40.57 mm"]],
    )
    uneven_rows = table_fixture(
        table_id="table_uneven",
        caption="Uneven rows",
        headers=["A", "B"],
        rows=[["one"], ["two", "three", "four"]],
    )
    latex_cell = table_fixture(
        table_id="table_latex",
        rows=[["$X_f$", "11.66 mm|nominal"]],
    )

    explicit_text = render_table_as_pipe_markdown(explicit_headers)
    no_header_text = render_table_as_pipe_markdown(no_headers)
    uneven_text = render_table_as_pipe_markdown(uneven_rows)
    latex_text = render_table_as_pipe_markdown(latex_cell)

    assert explicit_text == (
        "Parameter Table\n\n"
        "| Name | Value |\n"
        "|---|---|\n"
        "| Length | 31.43 mm |\n"
        "| Width | 40.57 mm |"
    )
    assert "| Column 1 | Column 2 |" in no_header_text
    assert "| Length | 31.43 mm |" in no_header_text
    assert "| A | B | Column 3 |" in uneven_text
    assert "| one |  |  |" in uneven_text
    assert "| two | three | four |" in uneven_text
    assert "| X_f | 11.66 mm\\|nominal |" in latex_text
    for text in (explicit_text, no_header_text, uneven_text, latex_text):
        lowered = text.lower()
        assert "<table" not in lowered
        assert "<tr" not in lowered
        assert "<td" not in lowered
        assert "<caption" not in lowered


def test_indexed_table_text_is_pipe_markdown_for_generic_tables(tmp_path) -> None:
    tables = [
        {
            "table_id": "table_002",
            "page": 3,
            "caption": None,
            "headers": [],
            "rows": [["Length", "31.43 mm"], ["Width", "40.57 mm"]],
            "units": ["mm"],
            "raw_markdown": "<table><tr><td>Length</td></tr></table>",
            "source": "parsed/document.nuextract.md",
        },
        {
            "table_id": "table_003",
            "page": 3,
            "caption": "Uneven rows",
            "headers": ["A", "B"],
            "rows": [["one"], ["two", "three", "four"]],
            "units": [],
            "raw_markdown": "<table><caption>Uneven rows</caption></table>",
            "source": "parsed/document.nuextract.md",
        },
        {
            "table_id": "table_004",
            "page": 3,
            "caption": "Feed point",
            "headers": ["Symbol", "Value"],
            "rows": [["$X_f$", "11.66 mm"]],
            "units": ["mm"],
            "raw_markdown": "<table><tr><td>$X_f$</td></tr></table>",
            "source": "parsed/document.nuextract.md",
        },
    ]
    run_dir = make_retrieval_run(tmp_path, additional_tables=tables)

    build_evidence_index_from_run(run_dir)

    no_headers = read_jsonl_item(run_dir, "table_002")["text"]
    uneven = read_jsonl_item(run_dir, "table_003")["text"]
    latex = read_jsonl_item(run_dir, "table_004")["text"]
    assert "| Column 1 | Column 2 |" in no_headers
    assert "| Width | 40.57 mm |" in no_headers
    assert uneven.startswith("Uneven rows\n\n| A | B | Column 3 |")
    assert "| one |  |  |" in uneven
    assert "| two | three | four |" in uneven
    assert "| X_f | 11.66 mm |" in latex
    for text in (no_headers, uneven, latex):
        lowered = text.lower()
        assert "<table" not in lowered
        assert "<tr" not in lowered
        assert "<td" not in lowered
        assert "<caption" not in lowered


def make_retrieval_run(
    tmp_path: Path,
    additional_tables: list[dict] | None = None,
) -> Path:
    run_dir = tmp_path / "run"
    write_fake_manifest(run_dir)
    blocks = [
        {
            "block_id": "page_1_block_001",
            "page": 1,
            "kind": "heading",
            "text": "Antenna Design",
            "source": "parsed/document.nuextract.md",
        },
        {
            "block_id": "page_1_block_002",
            "page": 1,
            "kind": "paragraph",
            "text": (
                "The proposed antenna uses an FR4 substrate with thickness "
                "h = 1.6 mm."
            ),
            "source": "parsed/document.nuextract.md",
        },
        {
            "block_id": "page_1_block_003",
            "page": 1,
            "kind": "figure_caption",
            "text": "Figure 1. Geometry of the proposed antenna.",
            "source": "parsed/document.nuextract.md",
        },
        {
            "block_id": "page_2_block_004",
            "page": 2,
            "kind": "table",
            "text": (
                "<table><caption>TABLE I ANTENNA PARAMETERS</caption>"
                "<tr><td>S1</td><td>92 mm</td></tr></table>"
            ),
            "source": "parsed/document.nuextract.md",
        },
    ]
    blocks_path = run_dir / "parsed/evidence_blocks.jsonl"
    blocks_path.parent.mkdir(parents=True, exist_ok=True)
    with blocks_path.open("w", encoding="utf-8") as file:
        for block in blocks:
            file.write(json.dumps(block) + "\n")

    tables = [
        {
            "table_id": "table_001",
            "page": 2,
            "caption": "TABLE I ANTENNA PARAMETERS",
            "headers": ["S1", "S2", "P1", "P2", "L1"],
            "rows": [["92", "96", "45", "68", "76"]],
            "units": ["mm"],
            "raw_markdown": "<table>...</table>",
            "source": "parsed/document.nuextract.md",
        }
    ]
    tables.extend(additional_tables or [])
    write_json(
        run_dir / "parsed/tables.json",
        {
            "source_markdown": "parsed/document.nuextract.md",
            "tables": tables,
        },
    )
    return run_dir


def table_fixture(
    table_id: str,
    rows: list[list[str]],
    caption: str | None = None,
    headers: list[str] | None = None,
) -> ExtractedTable:
    return ExtractedTable(
        table_id=table_id,
        page=1,
        caption=caption,
        headers=headers or [],
        rows=rows,
        units=[],
        raw_markdown="<table></table>",
        source="parsed/document.nuextract.md",
    )


def read_jsonl_item(run_dir: Path, evidence_id: str) -> dict:
    return next(
        item
        for item in read_jsonl(run_dir / "retrieval/evidence_index.jsonl")
        if item["evidence_id"] == evidence_id
    )


def write_fake_manifest(run_dir: Path) -> None:
    manifest = RunManifest(
        run_id="run_test",
        input_file="input/test.pdf",
        pipeline_version="0.1.0",
        phases={
            "run_infrastructure": PhaseStatus.COMPLETED,
            "page_rendering": PhaseStatus.COMPLETED,
            "nuextract_markdown": PhaseStatus.COMPLETED,
            "evidence_blocks": PhaseStatus.COMPLETED,
            "table_extraction": PhaseStatus.COMPLETED,
            "evidence_indexing": PhaseStatus.PENDING,
            "evidence_search": PhaseStatus.PENDING,
            "nuextract_raw_extraction": PhaseStatus.PENDING,
            "canonicalization": PhaseStatus.PENDING,
            "cst_integration_intent": PhaseStatus.PENDING,
        },
    )
    write_json(run_dir / "manifest.json", manifest.model_dump(mode="json"))
