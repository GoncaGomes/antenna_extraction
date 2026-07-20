from __future__ import annotations

import os
from pathlib import Path

import pytest

from antenna_ingest.orchestration.schemas import RunManifest
from antenna_ingest.utils.json_io import read_json, write_json
from scripts.freeze_benchmark import build_benchmark_manifest, main


def test_freeze_benchmark_rejects_invalid_run_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="run directory does not exist"):
        build_benchmark_manifest(
            [tmp_path / "missing"],
            benchmark_id="test",
        )


def test_freeze_benchmark_reads_legacy_manifest(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_legacy"
    checksum = "a" * 64
    write_json(
        run_dir / "manifest.json",
        {
            "run_id": "run_legacy",
            "input_file": "input/legacy.pdf",
            "pipeline_version": "0.1.0",
            "paper_id": "paper_legacy",
            "phase_status": {"canonicalization": "completed"},
            "artifacts": [
                {
                    "name": "source_pdf",
                    "relative_path": "input/legacy.pdf",
                    "producing_phase": "run_infrastructure",
                    "checksum": checksum,
                }
            ],
        },
    )

    benchmark = build_benchmark_manifest(
        [run_dir],
        benchmark_id="test",
    )

    entry = benchmark["runs"][0]
    assert entry["document_id"] == f"document_{checksum[:12]}"
    assert entry["input_sha256"] == checksum
    assert entry["canonicalization_phase_result"] == "completed"


def test_freeze_benchmark_writes_expected_minimal_manifest(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run_new"
    checksum = "b" * 64
    manifest = RunManifest(
        run_id="run_new",
        input_file="input/article.pdf",
        input_sha256=checksum,
        document_id=f"document_{checksum[:12]}",
        pipeline_version="0.1.0",
        paper_id="paper_001",
        phases={"canonicalization": "failed"},
    )
    write_json(
        run_dir / "manifest.json",
        manifest.model_dump(mode="json"),
    )
    output = tmp_path / "benchmark" / "manifest.json"

    exit_code = main(
        [
            str(run_dir),
            "--output",
            str(output),
            "--benchmark-id",
            "baseline_test",
        ]
    )

    assert exit_code == 0
    benchmark = read_json(output)
    assert benchmark["benchmark_id"] == "baseline_test"
    assert len(benchmark["runs"]) == 1
    entry = benchmark["runs"][0]
    assert entry == {
        "run_id": "run_new",
        "paper_id": "paper_001",
        "document_id": f"document_{checksum[:12]}",
        "input_filename": "article.pdf",
        "input_sha256": checksum,
        "pipeline_version": "0.1.0",
        "canonicalization_phase_result": "failed",
        "source_run_path": Path(
            os.path.relpath(run_dir.resolve(), Path.cwd().resolve())
        ).as_posix(),
    }
    assert isinstance(benchmark["created_at"], str)
