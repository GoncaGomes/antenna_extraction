from __future__ import annotations

import pytest
from pydantic import ValidationError

from antenna_ingest.nuextract.candidate_schemas import (
    AntennaDesignCandidate,
    CandidateSummary,
    EvidenceRef,
    ExtractedProperty,
    GeometryDescription,
    RECONSTRUCTION_STATUSES,
)


def test_minimal_candidate_validates() -> None:
    candidate = AntennaDesignCandidate.model_validate({})

    assert candidate.schema_name == "antenna_design_candidate_v2"


def test_invalid_schema_name_fails() -> None:
    with pytest.raises(ValidationError):
        AntennaDesignCandidate.model_validate(
            {"schema_name": "antenna_design_candidate_v1"}
        )


def test_extracted_property_with_all_empty_fields_validates() -> None:
    prop = ExtractedProperty(
        name=None,
        raw_value=None,
        value=None,
        unit=None,
        evidence=[],
        notes=[],
    )

    assert prop.is_empty() is True


@pytest.mark.parametrize(
    ("collection", "id_field"),
    [
        ("materials", "material_id"),
        ("components", "component_id"),
        ("features", "feature_id"),
        ("feeds", "feed_id"),
    ],
)
def test_duplicate_final_design_ids_fail(collection: str, id_field: str) -> None:
    with pytest.raises(ValidationError, match=f"duplicate {id_field}"):
        AntennaDesignCandidate.model_validate(
            {
                "final_design": {
                    collection: [
                        {id_field: "duplicate"},
                        {id_field: "duplicate"},
                    ]
                }
            }
        )


def test_unknown_operations_field_fails() -> None:
    with pytest.raises(ValidationError, match="operations"):
        AntennaDesignCandidate.model_validate({"operations": []})


def test_evidence_page_zero_fails() -> None:
    with pytest.raises(ValidationError):
        EvidenceRef(page=0)


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_evidence_confidence_outside_zero_to_one_fails(
    confidence: float,
) -> None:
    with pytest.raises(ValidationError):
        EvidenceRef(confidence=confidence)


@pytest.mark.parametrize("status", RECONSTRUCTION_STATUSES)
def test_valid_reconstruction_statuses_pass(status: str) -> None:
    summary = CandidateSummary(reconstruction_status=status)
    geometry = GeometryDescription(reconstruction_status=status)

    assert summary.reconstruction_status == status
    assert geometry.reconstruction_status == status


@pytest.mark.parametrize(
    "model_class",
    [CandidateSummary, GeometryDescription],
)
def test_invalid_reconstruction_status_fails(model_class) -> None:
    with pytest.raises(ValidationError, match="reconstruction_status"):
        model_class(reconstruction_status="ready_to_build")
