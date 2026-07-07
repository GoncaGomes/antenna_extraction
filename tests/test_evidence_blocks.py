from __future__ import annotations

import json
from pathlib import Path

import pytest

from antenna_ingest.evidence.blocks import (
    EVIDENCE_BLOCKS_PATH,
    EVIDENCE_BLOCKS_REPORT_PATH,
    build_evidence_blocks_from_run,
)
from antenna_ingest.orchestration.schemas import PhaseStatus, RunManifest
from antenna_ingest.utils.json_io import read_json, write_json


MARKDOWN = """\
<!-- page: 1 -->

# Antenna Design

The antenna uses an FR4 substrate.

Figure 1. Geometry of the proposed antenna.

<!-- page: 2 -->

<table>
<tr><th>L</th><th>W</th></tr>
<tr><td>20 mm</td><td>15 mm</td></tr>
</table>
"""


def test_build_evidence_blocks_writes_blocks_report_and_manifest(tmp_path) -> None:
    run_dir = _make_run(tmp_path, MARKDOWN)

    report = build_evidence_blocks_from_run(run_dir)

    assert (run_dir / EVIDENCE_BLOCKS_PATH).exists()
    assert (run_dir / EVIDENCE_BLOCKS_REPORT_PATH).exists()
    blocks = _read_jsonl(run_dir / EVIDENCE_BLOCKS_PATH)
    assert report.block_count == 4
    assert [block["page"] for block in blocks] == [1, 1, 1, 2]
    assert [block["block_id"] for block in blocks] == [
        "page_1_block_001",
        "page_1_block_002",
        "page_1_block_003",
        "page_2_block_001",
    ]
    assert {block["kind"] for block in blocks} == {
        "heading",
        "paragraph",
        "figure_caption",
        "table",
    }

    manifest = RunManifest.model_validate(read_json(run_dir / "manifest.json"))
    assert manifest.phase_status["evidence_blocks"] == PhaseStatus.COMPLETED
    artifact_names = {artifact.name for artifact in manifest.artifacts}
    assert {"evidence_blocks", "evidence_blocks_report"} <= artifact_names
    assert all(artifact.checksum for artifact in manifest.artifacts)


def test_evidence_blocks_force_controls_overwrite(tmp_path) -> None:
    run_dir = _make_run(tmp_path, MARKDOWN)
    build_evidence_blocks_from_run(run_dir)

    with pytest.raises(FileExistsError):
        build_evidence_blocks_from_run(run_dir)

    (run_dir / EVIDENCE_BLOCKS_PATH).write_text("stale\n", encoding="utf-8")
    report = build_evidence_blocks_from_run(run_dir, force=True)

    assert report.block_count == 4
    assert "stale" not in (run_dir / EVIDENCE_BLOCKS_PATH).read_text(
        encoding="utf-8"
    )


def _make_run(tmp_path: Path, markdown: str) -> Path:
    run_dir = tmp_path / "run"
    write_fake_manifest(run_dir)
    markdown_path = run_dir / "parsed/document.nuextract.md"
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(markdown, encoding="utf-8")
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
            "evidence_blocks": PhaseStatus.PENDING,
            "table_extraction": PhaseStatus.PENDING,
            "nuextract_raw_extraction": PhaseStatus.PENDING,
            "canonicalization": PhaseStatus.PENDING,
            "cst_integration_intent": PhaseStatus.PENDING,
        },
    )
    write_json(run_dir / "manifest.json", manifest.model_dump(mode="json"))


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
