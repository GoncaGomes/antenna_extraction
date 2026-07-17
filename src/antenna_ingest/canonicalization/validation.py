from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field

from antenna_ingest.canonicalization.schemas import CanonicalDesignRecord
from antenna_ingest.orchestration.schemas import StrictModel
from antenna_ingest.retrieval.index import (
    EVIDENCE_INDEX_PATH,
    EvidenceIndexItem,
    read_jsonl,
)


class EvidenceReferenceValidationReport(StrictModel):
    valid: bool
    referenced_evidence_ids: list[str] = Field(default_factory=list)
    unknown_evidence_ids: list[str] = Field(default_factory=list)


class CanonicalizationValidationReport(StrictModel):
    valid: bool
    evidence_references_valid: bool
    session_provenance_valid: bool
    referenced_evidence_count: int = Field(ge=0)
    retrieved_evidence_count: int = Field(ge=0)
    search_call_count: int = Field(ge=0)
    unknown_evidence_ids: list[str] = Field(default_factory=list)
    unretrieved_evidence_ids: list[str] = Field(default_factory=list)
    object_count: int = Field(ge=0)
    material_count: int = Field(ge=0)
    relationship_count: int = Field(ge=0)
    excitation_count: int = Field(ge=0)
    critical_missing_information_count: int = Field(ge=0)
    unresolved_conflict_count: int = Field(ge=0)


def collect_evidence_ids(record: CanonicalDesignRecord) -> list[str]:
    collected: list[str] = []
    seen: set[str] = set()

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            for field_name, field_value in value.items():
                if field_name == "evidence_ids":
                    for evidence_id in field_value:
                        if evidence_id not in seen:
                            seen.add(evidence_id)
                            collected.append(evidence_id)
                else:
                    collect(field_value)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(record.model_dump(mode="python"))
    return collected


def load_valid_evidence_ids(run_dir: Path) -> set[str]:
    index_path = Path(run_dir).resolve() / EVIDENCE_INDEX_PATH
    if not index_path.is_file():
        raise FileNotFoundError(f"evidence index does not exist: {index_path}")
    items = [
        EvidenceIndexItem.model_validate(item) for item in read_jsonl(index_path)
    ]
    return {item.evidence_id for item in items}


def validate_evidence_references(
    record: CanonicalDesignRecord,
    valid_evidence_ids: set[str],
) -> EvidenceReferenceValidationReport:
    referenced_ids = collect_evidence_ids(record)
    unknown_ids = [
        evidence_id
        for evidence_id in referenced_ids
        if evidence_id not in valid_evidence_ids
    ]
    return EvidenceReferenceValidationReport(
        valid=not unknown_ids,
        referenced_evidence_ids=referenced_ids,
        unknown_evidence_ids=unknown_ids,
    )


def build_canonicalization_validation_report(
    record: CanonicalDesignRecord,
    valid_evidence_ids: set[str],
    retrieved_evidence_ids: list[str],
    search_call_count: int,
) -> CanonicalizationValidationReport:
    evidence_report = validate_evidence_references(record, valid_evidence_ids)
    retrieved_ids = list(dict.fromkeys(retrieved_evidence_ids))
    retrieved_id_set = set(retrieved_ids)
    unretrieved_ids = [
        evidence_id
        for evidence_id in evidence_report.referenced_evidence_ids
        if evidence_id in valid_evidence_ids
        and evidence_id not in retrieved_id_set
    ]
    session_provenance_valid = not unretrieved_ids
    return CanonicalizationValidationReport(
        valid=evidence_report.valid and session_provenance_valid,
        evidence_references_valid=evidence_report.valid,
        session_provenance_valid=session_provenance_valid,
        referenced_evidence_count=len(evidence_report.referenced_evidence_ids),
        retrieved_evidence_count=len(retrieved_ids),
        search_call_count=search_call_count,
        unknown_evidence_ids=evidence_report.unknown_evidence_ids,
        unretrieved_evidence_ids=unretrieved_ids,
        object_count=len(record.objects),
        material_count=len(record.materials),
        relationship_count=len(record.relationships),
        excitation_count=len(record.excitations),
        critical_missing_information_count=sum(
            item.severity == "critical" for item in record.missing_information
        ),
        unresolved_conflict_count=sum(
            item.status == "unresolved" for item in record.conflicts
        ),
    )
