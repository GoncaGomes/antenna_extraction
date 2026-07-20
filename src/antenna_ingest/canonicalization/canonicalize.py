from __future__ import annotations

from pathlib import Path

from antenna_ingest.canonicalization.agent import (
    LATEST_MODEL_RESPONSE_PATH,
    RAW_MODEL_RESPONSE_PATH as AGENT_RAW_MODEL_RESPONSE_PATH,
    SEARCH_CHECKPOINT_PATH,
    CanonicalizationAgentResult,
    CanonicalizationCheckpointRecorder,
    run_canonicalization_agent,
)
from antenna_ingest.canonicalization.schemas import CanonicalDesignRecord
from antenna_ingest.canonicalization.validation import (
    CanonicalizationValidationReport,
    build_canonicalization_validation_report,
    load_valid_evidence_ids,
)
from antenna_ingest.nuextract.settings import NuExtractSettings
from antenna_ingest.orchestration.failures import write_failure_record
from antenna_ingest.orchestration.phases import complete_phase, fail_phase, start_phase
from antenna_ingest.orchestration.runs import load_run_manifest, sha256_file
from antenna_ingest.orchestration.schemas import (
    ArtifactReference,
    RunManifest,
)
from antenna_ingest.utils.json_io import write_json


CANONICALIZATION_PHASE = "canonicalization"
CANONICAL_DESIGN_RECORD_PATH = "canonicalization/canonical_design_record.json"
CANONICALIZATION_REPORT_PATH = "canonicalization/canonicalization_report.json"
RAW_MODEL_RESPONSE_PATH = AGENT_RAW_MODEL_RESPONSE_PATH
CANONICALIZATION_TRACE_PATH = "canonicalization/canonicalization_trace.json"


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
    agent_result = run_canonicalization_agent(
        run_dir,
        settings=settings,
        client=client,
        max_tool_calls=max_tool_calls,
        enable_thinking=enable_thinking,
    )
    return _validate_agent_result(run_dir, agent_result)


def _validate_agent_result(
    run_dir: Path,
    agent_result: CanonicalizationAgentResult,
) -> tuple[CanonicalDesignRecord, CanonicalizationValidationReport]:
    record = parse_canonical_design_response(agent_result.raw_response)
    return _validate_record_evidence(run_dir, agent_result, record)


def _validate_record_evidence(
    run_dir: Path,
    agent_result: CanonicalizationAgentResult,
    record: CanonicalDesignRecord,
) -> tuple[CanonicalDesignRecord, CanonicalizationValidationReport]:
    valid_evidence_ids = load_valid_evidence_ids(run_dir)
    report = build_canonicalization_validation_report(
        record,
        valid_evidence_ids,
        agent_result.retrieved_evidence_ids,
        len(agent_result.searches),
    )
    errors = []
    if report.unknown_evidence_ids:
        errors.append(
            "canonical design references unknown evidence IDs: "
            + ", ".join(report.unknown_evidence_ids)
        )
    if report.unretrieved_evidence_ids:
        errors.append(
            "canonical design references evidence IDs not retrieved during "
            "this run: "
            + ", ".join(report.unretrieved_evidence_ids)
        )
    if errors:
        raise ValueError(
            "; ".join(errors)
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
    manifest = load_run_manifest(manifest_path)
    refuse_existing_canonicalization_outputs(run_dir, force)

    start_phase(manifest, CANONICALIZATION_PHASE)
    write_json(manifest_path, manifest.model_dump(mode="json"))

    recorder = CanonicalizationCheckpointRecorder(run_dir)
    substage = "preparation"
    agent_completed = False
    try:
        agent_result = run_canonicalization_agent(
            run_dir,
            settings=settings,
            client=client,
            max_tool_calls=max_tool_calls,
            enable_thinking=enable_thinking,
            recorder=recorder,
        )
        agent_completed = True
        substage = "artifact writing"
        write_canonicalization_audit_outputs(run_dir, agent_result)
        substage = "structured response parsing"
        record = parse_canonical_design_response(agent_result.raw_response)
        substage = "evidence validation"
        record, report = _validate_record_evidence(run_dir, agent_result, record)
        substage = "artifact writing"
        write_json(
            run_dir / CANONICAL_DESIGN_RECORD_PATH,
            record.model_dump(mode="json"),
        )
        write_json(
            run_dir / CANONICALIZATION_REPORT_PATH,
            report.model_dump(mode="json"),
        )

        manifest = load_run_manifest(manifest_path)
        complete_phase(manifest, CANONICALIZATION_PHASE)
        replace_canonicalization_artifacts(manifest, run_dir)
        write_json(manifest_path, manifest.model_dump(mode="json"))
        return record, report
    except Exception as error:
        failed_manifest = load_run_manifest(manifest_path)
        if not agent_completed:
            substage = recorder.substage
        partial_artifacts = _existing_canonicalization_progress(run_dir)
        response_artifact = (
            RAW_MODEL_RESPONSE_PATH
            if (run_dir / RAW_MODEL_RESPONSE_PATH).is_file()
            else None
        )
        failure_reference = write_failure_record(
            run_dir,
            phase=CANONICALIZATION_PHASE,
            attempt=failed_manifest.phases[CANONICALIZATION_PHASE].attempt,
            substage=substage,
            error=error,
            response_artifact=response_artifact,
            partial_artifacts=partial_artifacts,
        )
        fail_phase(
            failed_manifest,
            CANONICALIZATION_PHASE,
            failure_reference,
        )
        write_json(manifest_path, failed_manifest.model_dump(mode="json"))
        raise


def refuse_existing_canonicalization_outputs(
    run_dir: Path,
    force: bool,
) -> None:
    paths = [
        Path(run_dir) / CANONICAL_DESIGN_RECORD_PATH,
        Path(run_dir) / CANONICALIZATION_REPORT_PATH,
        Path(run_dir) / RAW_MODEL_RESPONSE_PATH,
        Path(run_dir) / CANONICALIZATION_TRACE_PATH,
        Path(run_dir) / SEARCH_CHECKPOINT_PATH,
        Path(run_dir) / LATEST_MODEL_RESPONSE_PATH,
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
    artifact_names = {
        "canonical_design_record",
        "canonicalization_report",
        "canonicalization_raw_model_response",
        "canonicalization_trace",
    }
    manifest.artifacts = [
        artifact
        for artifact in manifest.artifacts
        if artifact.name not in artifact_names
    ]
    for name, relative_path in (
        ("canonical_design_record", CANONICAL_DESIGN_RECORD_PATH),
        ("canonicalization_report", CANONICALIZATION_REPORT_PATH),
        ("canonicalization_raw_model_response", RAW_MODEL_RESPONSE_PATH),
        ("canonicalization_trace", CANONICALIZATION_TRACE_PATH),
    ):
        manifest.add_artifact(
            ArtifactReference(
                name=name,
                relative_path=relative_path,
                producing_phase=CANONICALIZATION_PHASE,
                checksum=sha256_file(Path(run_dir) / relative_path),
            )
        )


def write_canonicalization_audit_outputs(
    run_dir: Path,
    agent_result: CanonicalizationAgentResult,
) -> None:
    raw_response_path = Path(run_dir) / RAW_MODEL_RESPONSE_PATH
    raw_response_path.parent.mkdir(parents=True, exist_ok=True)
    raw_response_path.write_text(
        agent_result.raw_response,
        encoding="utf-8",
        newline="",
    )
    write_json(
        Path(run_dir) / CANONICALIZATION_TRACE_PATH,
        agent_result.model_dump(mode="json", exclude={"raw_response"}),
    )


def _existing_canonicalization_progress(run_dir: Path) -> list[str]:
    paths = (
        RAW_MODEL_RESPONSE_PATH,
        CANONICALIZATION_TRACE_PATH,
        SEARCH_CHECKPOINT_PATH,
        LATEST_MODEL_RESPONSE_PATH,
    )
    return [path for path in paths if (Path(run_dir) / path).is_file()]
