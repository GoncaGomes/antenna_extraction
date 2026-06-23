from __future__ import annotations

import pytest
from pydantic import ValidationError

from antenna_ingest.nuextract.candidate_schemas import (
    AntennaDesignCandidate,
    ExtractedValue,
    SimulationSetupCandidate,
)


def test_minimal_candidate_validates() -> None:
    candidate = AntennaDesignCandidate.model_validate({})

    assert candidate.schema_name == "antenna_design_candidate_v1"


def test_extracted_value_with_all_null_fields_validates() -> None:
    value = ExtractedValue(
        name=None,
        value=None,
        numeric_value=None,
        unit=None,
        source_page=None,
        source_text=None,
        confidence=None,
    )

    assert value.is_empty() is True


def test_simulation_setup_accepts_empty_extracted_value_objects() -> None:
    empty_value = {
        "name": None,
        "value": None,
        "numeric_value": None,
        "unit": None,
        "source_page": None,
        "source_text": None,
        "confidence": None,
    }

    setup = SimulationSetupCandidate(
        software=empty_value,
        solver=empty_value,
        boundary_conditions=empty_value,
    )

    assert setup.software is not None and setup.software.is_empty()
    assert setup.solver is not None and setup.solver.is_empty()
    assert setup.boundary_conditions is not None
    assert setup.boundary_conditions.is_empty()


@pytest.mark.parametrize(
    ("collection", "id_field"),
    [
        ("components", "component_id"),
        ("materials", "material_id"),
        ("feeds", "feed_id"),
        ("geometry_features", "feature_id"),
    ],
)
def test_duplicate_final_design_ids_fail(collection: str, id_field: str) -> None:
    with pytest.raises(ValidationError, match=f"duplicate {id_field}"):
        AntennaDesignCandidate.model_validate(
            {
                "final_design_candidate": {
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


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_confidence_outside_zero_to_one_fails(confidence: float) -> None:
    with pytest.raises(ValidationError):
        AntennaDesignCandidate.model_validate(
            {
                "final_design_candidate": {
                    "final_design_evidence": [{"confidence": confidence}]
                }
            }
        )


def test_source_page_zero_fails() -> None:
    with pytest.raises(ValidationError):
        ExtractedValue(source_page=0)


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_extracted_value_confidence_outside_zero_to_one_fails(
    confidence: float,
) -> None:
    with pytest.raises(ValidationError):
        ExtractedValue(confidence=confidence)
