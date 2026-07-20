from __future__ import annotations

from pathlib import Path

import pytest

from antenna_ingest.evidence.tables import (
    TABLES_PATH,
    TABLES_REPORT_PATH,
    extract_tables_from_run,
)
from antenna_ingest.orchestration.schemas import PhaseStatus, RunManifest
from antenna_ingest.utils.json_io import read_json, write_json


MARKDOWN = """\
<!-- page: 3 -->

TABLE I

OPTIMIZED DIMENSIONS OF THE PROPOSED ANTENNA

<table>
<tr><th>S1</th><th>S2</th><th>P1</th><th>P2</th><th>L1</th></tr>
<tr><td>92</td><td>96</td><td>45</td><td>68</td><td>76</td></tr>
</table>
"""


def test_extract_tables_writes_document_report_and_manifest(tmp_path) -> None:
    run_dir = _make_run(tmp_path, MARKDOWN)

    report = extract_tables_from_run(run_dir)

    assert (run_dir / TABLES_PATH).exists()
    assert (run_dir / TABLES_REPORT_PATH).exists()
    document = read_json(run_dir / TABLES_PATH)
    assert report.table_count == 1
    assert len(document["tables"]) == 1
    table = document["tables"][0]
    assert table["table_id"] == "table_001"
    assert table["page"] == 3
    assert table["headers"] == ["S1", "S2", "P1", "P2", "L1"]
    assert table["rows"] == [["92", "96", "45", "68", "76"]]
    assert table["caption"] == "TABLE I OPTIMIZED DIMENSIONS OF THE PROPOSED ANTENNA"

    manifest = RunManifest.model_validate(read_json(run_dir / "manifest.json"))
    assert manifest.phases["table_extraction"].status == PhaseStatus.COMPLETED
    artifact_names = {artifact.name for artifact in manifest.artifacts}
    assert {"tables", "tables_report"} <= artifact_names
    assert all(artifact.checksum for artifact in manifest.artifacts)


def test_extract_tables_detects_units(tmp_path) -> None:
    markdown = """\
<!-- page: 1 -->

TABLE II (mm)

<table>
<tr><th>Length</th></tr>
<tr><td>20 mm</td></tr>
</table>
"""
    run_dir = _make_run(tmp_path, markdown)

    extract_tables_from_run(run_dir)

    table = read_json(run_dir / TABLES_PATH)["tables"][0]
    assert "mm" in table["units"]


def test_extract_tables_uses_html_caption(tmp_path) -> None:
    markdown = """\
<!-- page: 3 -->

<table>
  <caption>TABLE I<br>ANTENNA PARAMETERS</caption>
  <tbody>
    <tr><td>Length</td><td>31.43 mm</td></tr>
    <tr><td>Width</td><td>40.57 mm</td></tr>
    <tr><td>$X_f$</td><td>11.66 mm</td></tr>
    <tr><td>$Y_f$</td><td>20.29 mm</td></tr>
    <tr><td>$L_g$</td><td>41.19 mm</td></tr>
    <tr><td>$W_g$</td><td>50.32 mm</td></tr>
  </tbody>
</table>
"""
    run_dir = _make_run(tmp_path, markdown)

    extract_tables_from_run(run_dir)

    table = read_json(run_dir / TABLES_PATH)["tables"][0]
    assert table["caption"] == "TABLE I ANTENNA PARAMETERS"


def test_extract_tables_force_controls_overwrite(tmp_path) -> None:
    run_dir = _make_run(tmp_path, MARKDOWN)
    extract_tables_from_run(run_dir)

    with pytest.raises(FileExistsError):
        extract_tables_from_run(run_dir)

    (run_dir / TABLES_PATH).write_text("{}\n", encoding="utf-8")
    report = extract_tables_from_run(run_dir, force=True)

    assert report.table_count == 1
    assert len(read_json(run_dir / TABLES_PATH)["tables"]) == 1


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
        phases={
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
