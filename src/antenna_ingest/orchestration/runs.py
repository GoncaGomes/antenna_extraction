from __future__ import annotations

import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from antenna_ingest.orchestration.fingerprints import collect_run_fingerprint
from antenna_ingest.orchestration.phases import complete_phase, start_phase
from antenna_ingest.orchestration.schemas import (
    ArtifactReference,
    PhaseExecution,
    PhaseStatus,
    RunContext,
    RunManifest,
)
from antenna_ingest.utils.json_io import read_json, write_json


RUN_SUBDIRECTORIES = (
    "input",
    "parsed",
    "extraction",
    "retrieval",
    "canonicalization",
    "planning",
    "reports",
)

INITIAL_PHASE_STATUS = {
    "run_infrastructure": PhaseStatus.COMPLETED,
    "page_rendering": PhaseStatus.PENDING,
    "nuextract_markdown": PhaseStatus.PENDING,
    "evidence_blocks": PhaseStatus.PENDING,
    "table_extraction": PhaseStatus.PENDING,
    "evidence_indexing": PhaseStatus.PENDING,
    "evidence_search": PhaseStatus.PENDING,
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

    input_sha256 = sha256_file(input_pdf)
    document_id = document_id_from_sha256(input_sha256)

    for subdirectory in RUN_SUBDIRECTORIES:
        (run_dir / subdirectory).mkdir(parents=True, exist_ok=force)

    input_relative_path = Path("input") / input_pdf.name
    source_pdf = run_dir / input_relative_path
    shutil.copy2(input_pdf, source_pdf)

    manifest = RunManifest(
        run_id=run_id,
        input_file=input_relative_path.as_posix(),
        document_id=document_id,
        input_sha256=input_sha256,
        pipeline_version=pipeline_version,
        paper_id=paper_id,
        fingerprint=collect_run_fingerprint(),
        phases={
            name: PhaseExecution(status=status)
            for name, status in INITIAL_PHASE_STATUS.items()
        },
    )
    start_phase(manifest, "run_infrastructure")
    manifest.add_artifact(
        ArtifactReference(
            name="source_pdf",
            relative_path=input_relative_path.as_posix(),
            producing_phase="run_infrastructure",
            checksum=input_sha256,
        )
    )
    complete_phase(manifest, "run_infrastructure")
    write_json(run_dir / "manifest.json", manifest.model_dump(mode="json"))

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
    data = read_json(path)
    legacy_statuses = data.pop("phase_status", None)
    if "phases" not in data and isinstance(legacy_statuses, dict):
        data["schema_version"] = data.get("schema_version", "1.0")
        data["phases"] = {
            phase_name: {
                "status": status,
                "attempt": 0 if status == PhaseStatus.PENDING.value else 1,
                "started_at": None,
                "completed_at": None,
                "duration_seconds": None,
                "failure_reference": None,
            }
            for phase_name, status in legacy_statuses.items()
        }

    if not data.get("input_sha256"):
        artifacts = data.get("artifacts", [])
        source_artifact = next(
            (
                artifact
                for artifact in artifacts
                if artifact.get("name") == "source_pdf" and artifact.get("checksum")
            ),
            None,
        )
        if source_artifact is not None:
            data["input_sha256"] = source_artifact["checksum"]
    if not data.get("document_id") and data.get("input_sha256"):
        data["document_id"] = document_id_from_sha256(data["input_sha256"])
    return RunManifest.model_validate(data)


def _generate_run_id() -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"run_{timestamp}_{uuid4().hex[:8]}"
