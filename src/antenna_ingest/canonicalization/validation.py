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
