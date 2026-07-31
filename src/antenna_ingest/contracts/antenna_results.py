from __future__ import annotations

from typing import Literal

from pydantic import model_validator

from antenna_ingest.contracts.base import ContractModel
from antenna_ingest.contracts.common import (
    ConflictRecord,
    DesignRecord,
    DocumentReference,
    EvidenceRecord,
    MissingInformationRecord,
    PageRecord,
    ResultRecord,
    ResultsProvenance,
    ResultsStatus,
    Setup,
    validate_shared_references,
)


class AntennaResults(ContractModel):
    schema_name: Literal["antenna_results"]
    schema_version: Literal["1.0.0"]
    document: DocumentReference
    design_registry: list[DesignRecord]
    setups: list[Setup]
    results: list[ResultRecord]
    evidence_catalog: list[EvidenceRecord]
    conflicts: list[ConflictRecord]
    missing_information: list[MissingInformationRecord]
    provenance: ResultsProvenance
    status: ResultsStatus

    @model_validator(mode="after")
    def validate_referential_integrity(self) -> AntennaResults:
        declared_pages = [
            PageRecord(page_number=page_number)
            for page_number in range(1, self.document.page_count + 1)
        ]
        validate_shared_references(
            pages=declared_pages,
            evidence=self.evidence_catalog,
            designs=self.design_registry,
            setups=self.setups,
            results=self.results,
            conflicts=self.conflicts,
            missing_information=self.missing_information,
        )
        return self
