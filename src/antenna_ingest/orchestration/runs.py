from __future__ import annotations

import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from antenna_ingest.orchestration.schemas import (
    ArtifactReference,
    PhaseStatus,
    RunContext,
    RunManifest,
)
from antenna_ingest.utils.json_io import write_json


RUN_SUBDIRECTORIES = (
    "input",
    "parsed",
    "extraction",
    "canonicalization",
    "planning",
    "reports",
)

INITIAL_PHASE_STATUS = {
    "run_infrastructure": PhaseStatus.COMPLETED,
    "page_rendering": PhaseStatus.PENDING,
    "nuextract_markdown": PhaseStatus.PENDING,
    "nuextract_raw_extraction": PhaseStatus.PENDING,
    "canonicalization": PhaseStatus.PENDING,
    "cst_integration_intent": PhaseStatus.PENDING,
}


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

    for subdirectory in RUN_SUBDIRECTORIES:
        (run_dir / subdirectory).mkdir(parents=True, exist_ok=force)

    input_relative_path = Path("input") / input_pdf.name
    source_pdf = run_dir / input_relative_path
    shutil.copy2(input_pdf, source_pdf)

    manifest = RunManifest(
        run_id=run_id,
        input_file=input_relative_path.as_posix(),
        pipeline_version=pipeline_version,
        paper_id=paper_id,
        phase_status=dict(INITIAL_PHASE_STATUS),
    )
    manifest.add_artifact(
        ArtifactReference(
            name="source_pdf",
            relative_path=input_relative_path.as_posix(),
            producing_phase="run_infrastructure",
            checksum=sha256_file(source_pdf),
        )
    )
    write_json(run_dir / "manifest.json", manifest.model_dump(mode="json"))

    return RunContext(
        run_id=run_id,
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


def _generate_run_id() -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"run_{timestamp}_{uuid4().hex[:8]}"
