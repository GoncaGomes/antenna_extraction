from __future__ import annotations

import pytest

from antenna_ingest.orchestration.runs import create_run
from antenna_ingest.orchestration.schemas import RunManifest
from antenna_ingest.utils.json_io import read_json


def test_create_run_creates_phase_1_run_structure(tmp_path) -> None:
    article_pdf = tmp_path / "article.pdf"
    article_pdf.write_bytes(b"%PDF-1.4\n%fake test pdf\n")
    runs_root = tmp_path / "runs"

    context = create_run(article_pdf, runs_root=runs_root)
    run_dir = context.run_dir
    copied_pdf = run_dir / "input" / article_pdf.name

    assert run_dir.exists()
    assert copied_pdf.exists()
    assert (run_dir / "manifest.json").exists()
    assert copied_pdf.read_bytes() == article_pdf.read_bytes()

    for folder in (
        "input",
        "parsed",
        "extraction",
        "retrieval",
        "canonicalization",
        "planning",
        "reports",
    ):
        assert (run_dir / folder).is_dir()

    manifest = RunManifest.model_validate(read_json(run_dir / "manifest.json"))

    assert manifest.phase_status["run_infrastructure"] == "completed"
    downstream_phases = {
        phase: status
        for phase, status in manifest.phase_status.items()
        if phase != "run_infrastructure"
    }
    assert downstream_phases
    assert all(status == "pending" for status in downstream_phases.values())

    assert len(manifest.artifacts) == 1
    source_pdf = manifest.artifacts[0]
    assert source_pdf.name == "source_pdf"
    assert manifest.input_file == f"input/{article_pdf.name}"
    assert source_pdf.relative_path == f"input/{article_pdf.name}"
    assert source_pdf.producing_phase == "run_infrastructure"
    assert source_pdf.checksum

    for downstream_file in (
        "parsed/document.nuextract.md",
        "parsed/page_render_report.json",
        "extraction/nuextract_raw.json",
        "extraction/nuextract_raw_report.json",
        "retrieval/evidence_index.jsonl",
        "retrieval/evidence_index_report.json",
        "retrieval/query_trace.json",
        "canonicalization/canonical_antenna_record.json",
        "planning/cst_integration_intent.json",
    ):
        assert not (run_dir / downstream_file).exists()


def test_create_run_raises_for_missing_input_file(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        create_run(tmp_path / "missing.pdf", runs_root=tmp_path / "runs")


def test_create_run_persists_paper_id(tmp_path) -> None:
    article_pdf = tmp_path / "article.pdf"
    article_pdf.write_bytes(b"%PDF-1.4\n%fake test pdf\n")

    context = create_run(
        article_pdf,
        runs_root=tmp_path / "runs",
        paper_id="example_paper",
    )
    manifest = RunManifest.model_validate(read_json(context.run_dir / "manifest.json"))

    assert manifest.paper_id == "example_paper"
