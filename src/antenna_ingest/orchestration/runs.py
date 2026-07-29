from __future__ import annotations

import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from antenna_ingest.orchestration.fingerprints import collect_run_fingerprint
from antenna_ingest.orchestration.phases import (
    complete_phase,
    fail_phase,
    start_phase,
)
from antenna_ingest.orchestration.schemas import (
    RUN_PHASES,
    ArtifactReference,
    PhaseExecution,
    PhaseStatus,
    RunContext,
    RunManifest,
)
from antenna_ingest.utils.json_io import read_json, write_json


RUN_SUBDIRECTORIES = (
    "input",
    "pages",
    "extraction",
    "architecture",
    "outputs",
    "reports/failures",
)


def create_run(
    input_pdf: Path,
    runs_root: Path = Path("runs"),
    force: bool = False,
    pipeline_version: str = "0.1.0",
    paper_id: str | None = None,
) -> RunContext:
    input_pdf = Path(input_pdf)
    runs_root = Path(runs_root)

    if not input_pdf.exists():
        raise FileNotFoundError(f"input PDF does not exist: {input_pdf}")
    if not input_pdf.is_file():
        raise ValueError(f"input PDF is not a file: {input_pdf}")

    run_id = _generate_run_id()
    run_dir = runs_root / run_id
    if run_dir.exists() and not force:
        raise FileExistsError(f"run directory already exists: {run_dir}")

    input_sha256 = sha256_file(input_pdf)
    document_id = document_id_from_sha256(input_sha256)
    input_relative_path = Path("input") / input_pdf.name
    manifest_path = run_dir / "manifest.json"

    for subdirectory in RUN_SUBDIRECTORIES:
        (run_dir / subdirectory).mkdir(parents=True, exist_ok=force)

    manifest = RunManifest(
        run_id=run_id,
        input_file=input_relative_path.as_posix(),
        document_id=document_id,
        input_sha256=input_sha256,
        pipeline_version=pipeline_version,
        paper_id=paper_id,
        fingerprint=collect_run_fingerprint(),
        phases={
            phase_name: PhaseExecution(status=PhaseStatus.PENDING)
            for phase_name in RUN_PHASES
        },
    )
    start_phase(manifest, "run_initialization")
    write_json(manifest_path, manifest.model_dump(mode="json"))

    try:
        source_pdf = run_dir / input_relative_path
        shutil.copy2(input_pdf, source_pdf)
        manifest.add_artifact(
            ArtifactReference(
                name="source_pdf",
                relative_path=input_relative_path.as_posix(),
                producing_phase="run_initialization",
                checksum=input_sha256,
            )
        )
        complete_phase(
            manifest,
            "run_initialization",
            output_artifact_names=["source_pdf"],
        )
        write_json(manifest_path, manifest.model_dump(mode="json"))
    except Exception:
        fail_phase(manifest, "run_initialization", None)
        write_json(manifest_path, manifest.model_dump(mode="json"))
        raise

    return RunContext(
        run_id=run_id,
        document_id=document_id,
        input_sha256=input_sha256,
        input_path=input_pdf,
        run_dir=run_dir,
        pipeline_version=pipeline_version,
        paper_id=paper_id,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def document_id_from_sha256(checksum: str) -> str:
    return f"document_{checksum[:12]}"


def load_run_manifest(path: Path) -> RunManifest:
    return RunManifest.model_validate(read_json(path))


def _generate_run_id() -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"run_{timestamp}_{uuid4().hex[:8]}"
