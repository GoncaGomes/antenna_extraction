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
) -> tuple[CanonicalDesignRecord, CanonicalizationValidationReport]:
    raw_response = run_canonicalization_agent(
        run_dir,
        settings=settings,
        client=client,
        max_tool_calls=max_tool_calls,
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
