from __future__ import annotations

import platform
from pathlib import Path

import pytest

from antenna_ingest.orchestration.runs import create_run, sha256_file
from antenna_ingest.orchestration.schemas import (
    MANIFEST_SCHEMA_VERSION,
    RUN_PHASES,
    RunManifest,
)
from antenna_ingest.utils.json_io import read_json


def test_create_run_creates_minimal_foundation(tmp_path) -> None:
    article_pdf = tmp_path / "article.pdf"
    article_pdf.write_bytes(b"%PDF-1.4\n%fake test pdf\n")

    context = create_run(article_pdf, runs_root=tmp_path / "runs")
    run_dir = context.run_dir
    copied_pdf = run_dir / "input" / article_pdf.name

    assert copied_pdf.read_bytes() == article_pdf.read_bytes()
    assert (run_dir / "manifest.json").is_file()
    for folder in (
        "input",
        "pages",
        "extraction",
        "architecture",
        "outputs",
        "reports",
        "reports/failures",
    ):
        assert (run_dir / folder).is_dir()
    for legacy_folder in (
        "parsed",
        "retrieval",
        "canonicalization",
        "planning",
        "document",
        "model_traces",
        "cache",
    ):
        assert not (run_dir / legacy_folder).exists()

    manifest = RunManifest.model_validate(read_json(run_dir / "manifest.json"))
    assert manifest.schema_version == MANIFEST_SCHEMA_VERSION
    assert tuple(manifest.phases) == RUN_PHASES
    assert manifest.phases["run_initialization"].status == "completed"
    assert manifest.phases["run_initialization"].attempt == 1
    assert manifest.phases["run_initialization"].output_artifact_names == [
        "source_pdf"
    ]
    assert all(
        manifest.phases[name].status == "pending"
        for name in RUN_PHASES
        if name != "run_initialization"
    )

    assert len(manifest.artifacts) == 1
    source_pdf = manifest.artifacts[0]
    assert source_pdf.name == "source_pdf"
    assert manifest.input_file == f"input/{article_pdf.name}"
    assert source_pdf.relative_path == f"input/{article_pdf.name}"
    assert source_pdf.producing_phase == "run_initialization"
    assert source_pdf.checksum == sha256_file(copied_pdf)
    assert manifest.input_sha256 == source_pdf.checksum
    assert manifest.document_id == f"document_{source_pdf.checksum[:12]}"
    assert context.input_sha256 == manifest.input_sha256
    assert context.document_id == manifest.document_id
    assert manifest.fingerprint.python_version == platform.python_version()
    assert manifest.fingerprint.platform == platform.platform()
    assert manifest.fingerprint.pyproject_sha256 == sha256_file(
        Path("pyproject.toml")
    )
    assert manifest.fingerprint.lockfile_sha256 == sha256_file(Path("uv.lock"))

    assert list((run_dir / "extraction").iterdir()) == []
    assert list((run_dir / "architecture").iterdir()) == []
    assert list((run_dir / "outputs").iterdir()) == []


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


def test_document_identity_depends_on_pdf_bytes(tmp_path) -> None:
    first = tmp_path / "first.pdf"
    renamed = tmp_path / "renamed.pdf"
    modified = tmp_path / "modified.pdf"
    first.write_bytes(b"%PDF-1.4\n%same content\n")
    renamed.write_bytes(first.read_bytes())
    modified.write_bytes(b"%PDF-1.4\n%different content\n")

    first_run = create_run(first, runs_root=tmp_path / "runs_a")
    renamed_run = create_run(renamed, runs_root=tmp_path / "runs_b")
    modified_run = create_run(modified, runs_root=tmp_path / "runs_c")

    assert first_run.document_id == renamed_run.document_id
    assert first_run.input_sha256 == renamed_run.input_sha256
    assert first_run.document_id != modified_run.document_id
    assert first_run.input_sha256 != modified_run.input_sha256


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

    assert manifest.fingerprint.git_commit is None
    assert manifest.fingerprint.git_dirty is None
