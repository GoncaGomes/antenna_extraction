from __future__ import annotations

import json
from pathlib import Path

import pytest

from antenna_ingest.orchestration.schemas import PhaseStatus, RunManifest
from antenna_ingest.retrieval.index import (
    EVIDENCE_INDEX_PATH,
    EVIDENCE_INDEX_REPORT_PATH,
    build_evidence_index_from_run,
    read_jsonl,
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

    heading, paragraph, figure, table = items
    assert heading["next_id"] == paragraph["evidence_id"]
    assert paragraph["previous_id"] == heading["evidence_id"]
    assert paragraph["next_id"] == figure["evidence_id"]
    assert figure["previous_id"] == paragraph["evidence_id"]
    assert paragraph["section"] == "Antenna Design"
    assert table["evidence_id"] == "table_001"
    assert table["source_type"] == "table"
    assert {"S1", "S2", "P1", "P2", "L1"} <= set(table["key_tokens"])
    assert {"92", "96", "45", "68", "76"} <= set(table["numbers"])
    assert "mm" in table["units"]

    manifest = RunManifest.model_validate(read_json(run_dir / "manifest.json"))
    assert manifest.phase_status["evidence_indexing"] == PhaseStatus.COMPLETED
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
            "caption": "TABLE I. OPTIMIZED DIMENSIONS OF THE PROPOSED ANTENNA",
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


def write_fake_manifest(run_dir: Path) -> None:
    manifest = RunManifest(
        run_id="run_test",
        input_file="input/test.pdf",
        pipeline_version="0.1.0",
        phase_status={
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
