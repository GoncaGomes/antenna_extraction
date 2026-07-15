from __future__ import annotations

from pathlib import Path

from antenna_ingest.canonicalization.agent import run_canonicalization_agent
from antenna_ingest.canonicalization.schemas import CanonicalDesignRecord
from antenna_ingest.canonicalization.validation import (
    CanonicalizationValidationReport,
    build_canonicalization_validation_report,
    load_valid_evidence_ids,
)
from antenna_ingest.nuextract.settings import NuExtractSettings
from antenna_ingest.orchestration.runs import sha256_file
from antenna_ingest.orchestration.schemas import (
    ArtifactReference,
    PhaseStatus,
    RunManifest,
)
from antenna_ingest.utils.json_io import read_json, write_json


CANONICALIZATION_PHASE = "canonicalization"
CANONICAL_DESIGN_RECORD_PATH = "canonicalization/canonical_design_record.json"
CANONICALIZATION_REPORT_PATH = "canonicalization/canonicalization_report.json"


def parse_canonical_design_response(
    response_text: str,
) -> CanonicalDesignRecord:
    return CanonicalDesignRecord.model_validate_json(response_text)


def run_validated_canonicalization(
    run_dir: Path,
    *,
    settings: NuExtractSettings | None = None,
    client: object | None = None,
    max_tool_calls: int = 12,
    enable_thinking: bool = True,
) -> tuple[CanonicalDesignRecord, CanonicalizationValidationReport]:
    raw_response = run_canonicalization_agent(
        run_dir,
        settings=settings,
        client=client,
        max_tool_calls=max_tool_calls,
        enable_thinking=enable_thinking,
    )
    record = parse_canonical_design_response(raw_response)
    valid_evidence_ids = load_valid_evidence_ids(run_dir)
    report = build_canonicalization_validation_report(
        record,
        valid_evidence_ids,
    )
    if not report.valid:
        raise ValueError(
            "canonical design references unknown evidence IDs: "
            + ", ".join(report.unknown_evidence_ids)
        )
    return record, report


def canonicalize_run(
    run_dir: Path,
    *,
    force: bool = False,
    settings: NuExtractSettings | None = None,
    client: object | None = None,
    max_tool_calls: int = 12,
    enable_thinking: bool = True,
) -> tuple[CanonicalDesignRecord, CanonicalizationValidationReport]:
    run_dir = Path(run_dir).resolve()
    manifest_path = run_dir / "manifest.json"
    manifest = RunManifest.model_validate(read_json(manifest_path))
    refuse_existing_canonicalization_outputs(run_dir, force)

    manifest.phase_status[CANONICALIZATION_PHASE] = PhaseStatus.RUNNING
    write_json(manifest_path, manifest.model_dump(mode="json"))

    try:
        record, report = run_validated_canonicalization(
            run_dir,
            settings=settings,
            client=client,
            max_tool_calls=max_tool_calls,
            enable_thinking=enable_thinking,
        )
        write_json(
            run_dir / CANONICAL_DESIGN_RECORD_PATH,
            record.model_dump(mode="json"),
        )
        write_json(
            run_dir / CANONICALIZATION_REPORT_PATH,
            report.model_dump(mode="json"),
        )

        manifest = RunManifest.model_validate(read_json(manifest_path))
        manifest.phase_status[CANONICALIZATION_PHASE] = PhaseStatus.COMPLETED
        replace_canonicalization_artifacts(manifest, run_dir)
        write_json(manifest_path, manifest.model_dump(mode="json"))
        return record, report
    except Exception:
        failed_manifest = RunManifest.model_validate(read_json(manifest_path))
        failed_manifest.phase_status[CANONICALIZATION_PHASE] = PhaseStatus.FAILED
        write_json(manifest_path, failed_manifest.model_dump(mode="json"))
        raise


def refuse_existing_canonicalization_outputs(
    run_dir: Path,
    force: bool,
) -> None:
    paths = [
        Path(run_dir) / CANONICAL_DESIGN_RECORD_PATH,
        Path(run_dir) / CANONICALIZATION_REPORT_PATH,
    ]
    existing = [path for path in paths if path.exists()]
    if existing and not force:
        raise FileExistsError(
            f"canonicalization output already exists: {existing[0]}"
        )
    for path in existing:
        path.unlink()


def replace_canonicalization_artifacts(
    manifest: RunManifest,
    run_dir: Path,
) -> None:
    artifact_names = {"canonical_design_record", "canonicalization_report"}
    manifest.artifacts = [
        artifact
        for artifact in manifest.artifacts
        if artifact.name not in artifact_names
    ]
    for name, relative_path in (
        ("canonical_design_record", CANONICAL_DESIGN_RECORD_PATH),
        ("canonicalization_report", CANONICALIZATION_REPORT_PATH),
    ):
        manifest.add_artifact(
            ArtifactReference(
                name=name,
                relative_path=relative_path,
                producing_phase=CANONICALIZATION_PHASE,
                checksum=sha256_file(Path(run_dir) / relative_path),
            )
        )
