from __future__ import annotations

import pytest
from pydantic import ValidationError

from antenna_ingest.nuextract.candidate_schemas import (
    AntennaDesignCandidate,
    CandidateSummary,
    EvidenceRef,
    ExtractedProperty,
    FeatureCandidate,
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
        symbol=None,
        raw_value=None,
        value=None,
        unit=None,
        evidence=[],
        notes=[],
    )

    assert prop.is_empty() is True


def test_extracted_property_symbol_validates() -> None:
    prop = ExtractedProperty(symbol="Xf")

    assert prop.symbol == "Xf"


def test_extracted_property_with_symbol_is_not_empty() -> None:
    prop = ExtractedProperty(symbol="Xf")

    assert prop.is_empty() is False


def test_geometry_topological_relationship_validates() -> None:
    geometry = GeometryDescription(
        topological_relationship="printed on one side of the substrate"
    )

    assert (
        geometry.topological_relationship
        == "printed on one side of the substrate"
    )


def test_feature_topological_relationship_validates() -> None:
    feature = FeatureCandidate(
        feature_id="slot_1",
        topological_relationship="slot etched in the patch",
    )

    assert feature.topological_relationship == "slot etched in the patch"


@pytest.mark.parametrize(
    ("model_class", "kwargs"),
    [
        (GeometryDescription, {"location": "printed on substrate"}),
        (FeatureCandidate, {"feature_id": "slot_1", "location": "etched in patch"}),
    ],
)
def test_old_location_field_fails(model_class, kwargs) -> None:
    with pytest.raises(ValidationError, match="location"):
        model_class(**kwargs)


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
