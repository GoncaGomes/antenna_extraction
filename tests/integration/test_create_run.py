from __future__ import annotations

import platform
from pathlib import Path

import pytest

from antenna_ingest.orchestration.runs import create_run, sha256_file
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

    assert manifest.phases["run_infrastructure"].status == "completed"
    downstream_phases = {
        phase: execution
        for phase, execution in manifest.phases.items()
        if phase != "run_infrastructure"
    }
    assert downstream_phases
    assert all(
        execution.status == "pending"
        for execution in downstream_phases.values()
    )

    assert len(manifest.artifacts) == 1
    source_pdf = manifest.artifacts[0]
    assert source_pdf.name == "source_pdf"
    assert manifest.input_file == f"input/{article_pdf.name}"
    assert source_pdf.relative_path == f"input/{article_pdf.name}"
    assert source_pdf.producing_phase == "run_infrastructure"
    assert source_pdf.checksum == sha256_file(copied_pdf)
    assert manifest.input_sha256 == source_pdf.checksum
    assert manifest.document_id == f"document_{source_pdf.checksum[:12]}"
    assert context.input_sha256 == manifest.input_sha256
    assert context.document_id == manifest.document_id
    assert manifest.fingerprint is not None
    assert manifest.fingerprint.python_version == platform.python_version()
    assert manifest.fingerprint.platform == platform.platform()
    assert manifest.fingerprint.pyproject_sha256 == sha256_file(
        Path("pyproject.toml")
    )
    assert manifest.fingerprint.lockfile_sha256 == sha256_file(Path("uv.lock"))

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


def test_same_pdf_bytes_have_stable_document_id_across_filenames(tmp_path) -> None:
    first = tmp_path / "first.pdf"
    second = tmp_path / "renamed.pdf"
    content = b"%PDF-1.4\n%same content\n"
    first.write_bytes(content)
    second.write_bytes(content)

    first_run = create_run(first, runs_root=tmp_path / "runs_a")
    second_run = create_run(second, runs_root=tmp_path / "runs_b")

    assert first_run.document_id == second_run.document_id
    assert first_run.input_sha256 == second_run.input_sha256


def test_modified_pdf_bytes_have_different_document_ids(tmp_path) -> None:
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    first.write_bytes(b"%PDF-1.4\n%first\n")
    second.write_bytes(b"%PDF-1.4\n%second\n")

    first_run = create_run(first, runs_root=tmp_path / "runs_a")
    second_run = create_run(second, runs_root=tmp_path / "runs_b")

    assert first_run.document_id != second_run.document_id
    assert first_run.input_sha256 != second_run.input_sha256


def test_git_metadata_failure_does_not_prevent_run_creation(
    tmp_path,
    monkeypatch,
) -> None:
    article_pdf = tmp_path / "article.pdf"
    article_pdf.write_bytes(b"%PDF-1.4\n%fake\n")

    def fail_git(*_args, **_kwargs):
        raise OSError("git unavailable")

    monkeypatch.setattr(
        "antenna_ingest.orchestration.fingerprints.subprocess.run",
        fail_git,
    )

    context = create_run(article_pdf, runs_root=tmp_path / "runs")
    manifest = RunManifest.model_validate(read_json(context.run_dir / "manifest.json"))

    assert manifest.fingerprint is not None
    assert manifest.fingerprint.git_commit is None
    assert manifest.fingerprint.git_dirty is None
