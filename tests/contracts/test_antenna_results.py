from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from antenna_ingest.contracts.antenna_results import AntennaResults
from antenna_ingest.contracts.common import (
    IntervalRepresentation,
    ResultRecord,
    UnavailableRepresentation,
)


FIXTURE_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "contracts"
    / "minimal_antenna_results.json"
)


def _source_value(value: str, unit: str | None = None) -> dict:
    return {
        "value": value,
        "unit": unit,
        "qualifier": None,
        "legibility": "clear",
    }


def test_json_fixture_validates_at_the_serialized_boundary() -> None:
    validated = AntennaResults.model_validate_json(
        FIXTURE_PATH.read_text(encoding="utf-8")
    )

    assert validated.schema_name == "antenna_results"
    assert validated.schema_version == "1.0.0"


REPRESENTATIONS = [
    (
        "scalar",
        {"kind": "scalar", "value": _source_value("47.98", "ohm")},
    ),
    (
        "interval",
        {
            "kind": "interval",
            "lower": _source_value("2.40", "GHz"),
            "upper": _source_value("2.50", "GHz"),
        },
    ),
    (
        "point_collection",
        {
            "kind": "point_collection",
            "points": [
                {
                    "values": [
                        {"name": "frequency", "value": _source_value("2.450", "GHz")},
                        {"name": "gain", "value": _source_value("4.2", "dBi")},
                    ],
                    "label": "annotated point",
                }
            ],
        },
    ),
    (
        "sampled_series",
        {
            "kind": "sampled_series",
            "x_axis": {"name": "frequency", "unit": "GHz"},
            "y_axis": {"name": "S11", "unit": "dB"},
            "trace_label": "measured",
            "points": [
                {
                    "x": _source_value("2.450", "GHz"),
                    "y": _source_value("-10", "dB"),
                }
            ],
        },
    ),
    (
        "matrix",
        {
            "kind": "matrix",
            "rows": [[_source_value("1"), _source_value("0")]],
            "row_labels": ["row 1"],
            "column_labels": ["col 1", "col 2"],
        },
    ),
    (
        "angular_pattern",
        {
            "kind": "angular_pattern",
            "angular_coordinate": "theta",
            "angular_unit": "degree",
            "plane_or_cut": "phi = 0 degrees",
            "fixed_angle": _source_value("0", "degree"),
            "component_or_polarization": "co-polar",
            "radial_quantity": "gain",
            "points": [
                {
                    "angle": _source_value("0", "degree"),
                    "value": _source_value("4.2", "dBi"),
                }
            ],
        },
    ),
    (
        "spatial_map",
        {
            "kind": "spatial_map",
            "quantity": "surface current magnitude",
            "content": {
                "kind": "sampled",
                "coordinate_description": "reported local x-y coordinates",
                "samples": [
                    {
                        "values": [
                            {"name": "x", "value": _source_value("0", "mm")},
                            {
                                "name": "magnitude",
                                "value": _source_value("1.2", "A/m"),
                            },
                        ],
                        "label": None,
                    }
                ],
            },
        },
    ),
    (
        "image_only",
        {
            "kind": "image_only",
            "axes": [
                {"name": "frequency", "unit": "GHz"},
                {"name": "gain", "unit": "dBi"},
            ],
            "trace_labels": ["measured"],
            "annotated_points": [],
            "evidence_ids": ["ev_measured"],
        },
    ),
    (
        "qualitative",
        {
            "kind": "qualitative",
            "observation": "The measured response remains stable.",
        },
    ),
    (
        "unavailable",
        {
            "kind": "unavailable",
            "reason": "not_reported",
            "description": "The result is identified but no value is reported.",
        },
    ),
]


@pytest.mark.parametrize(("kind", "representation"), REPRESENTATIONS)
def test_all_result_representations_validate(
    antenna_results_data,
    kind,
    representation,
) -> None:
    data = deepcopy(antenna_results_data)
    result = data["results"][0]
    result["setup_id"] = None
    result["representation"] = representation
    data["results"] = [result]
    data["conflicts"] = []

    validated = AntennaResults.model_validate(data)

    assert validated.results[0].representation.kind == kind


def test_simulated_and_measured_results_remain_separate(
    antenna_results_data,
) -> None:
    data = deepcopy(antenna_results_data)
    data["conflicts"] = []

    results = AntennaResults.model_validate(data)

    assert [result.origin for result in results.results] == [
        "simulated",
        "measured",
    ]
    assert {result.result_id for result in results.results} == {
        "result_simulated",
        "result_measured",
    }
    assert all(result.design_id == "design_final" for result in results.results)
    assert results.conflicts == []


def test_result_record_excludes_removed_status_fields(antenna_results_data) -> None:
    assert "legibility" not in ResultRecord.model_fields
    assert "extraction_completeness" not in ResultRecord.model_fields
    assert "uncertainty_note" in ResultRecord.model_fields

    data = deepcopy(antenna_results_data)
    data["results"][0]["legibility"] = "clear"
    data["results"][0]["extraction_completeness"] = "complete"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        AntennaResults.model_validate(data)


def test_unspecified_result_origin_is_valid(antenna_results_data) -> None:
    data = deepcopy(antenna_results_data)
    data["results"][0]["origin"] = "unspecified"

    validated = AntennaResults.model_validate(data)

    assert validated.results[0].origin == "unspecified"


@pytest.mark.parametrize(
    "quantity",
    ["SAR", "surface current", "electric field", "gain", "power density"],
)
def test_spatial_map_supports_generic_quantities(
    antenna_results_data,
    quantity,
) -> None:
    data = deepcopy(antenna_results_data)
    data["results"][0]["representation"] = {
        "kind": "spatial_map",
        "quantity": quantity,
        "content": {
            "kind": "sampled",
            "coordinate_description": "reported local coordinates",
            "samples": [
                {
                    "values": [
                        {"name": "x", "value": _source_value("0", "mm")},
                        {"name": quantity, "value": _source_value("1.2")},
                    ],
                    "label": None,
                }
            ],
        },
    }

    validated = AntennaResults.model_validate(data)
    representation = validated.results[0].representation

    assert representation.kind == "spatial_map"
    assert representation.quantity == quantity


def test_sampled_spatial_map_without_samples_is_rejected(
    antenna_results_data,
) -> None:
    data = deepcopy(antenna_results_data)
    data["results"][0]["representation"] = {
        "kind": "spatial_map",
        "quantity": "electric field magnitude",
        "content": {
            "kind": "sampled",
            "coordinate_description": "reported local x-y coordinates",
            "samples": [],
        },
    }

    with pytest.raises(ValidationError, match="at least 1 item"):
        AntennaResults.model_validate(data)


def test_image_only_spatial_map_with_known_evidence_is_valid(
    antenna_results_data,
) -> None:
    data = deepcopy(antenna_results_data)
    data["results"][0]["representation"] = {
        "kind": "spatial_map",
        "quantity": "surface current magnitude",
        "content": {
            "kind": "image_only",
            "map_type_or_component": "surface current magnitude",
            "plane_or_cut": "radiator plane",
            "legend_or_scale_label": "A/m",
            "annotated_points": [],
            "evidence_ids": ["ev_simulated"],
        },
    }

    validated = AntennaResults.model_validate(data)

    assert validated.results[0].representation.content.kind == "image_only"
    assert validated.results[0].representation.content.evidence_ids == ["ev_simulated"]


def test_image_only_spatial_map_requires_evidence(antenna_results_data) -> None:
    data = deepcopy(antenna_results_data)
    data["results"][0]["representation"] = {
        "kind": "spatial_map",
        "quantity": "surface current magnitude",
        "content": {
            "kind": "image_only",
            "evidence_ids": [],
        },
    }

    with pytest.raises(ValidationError, match="at least 1 item"):
        AntennaResults.model_validate(data)


def test_image_only_spatial_map_rejects_unknown_evidence(
    antenna_results_data,
) -> None:
    data = deepcopy(antenna_results_data)
    data["results"][0]["representation"] = {
        "kind": "spatial_map",
        "quantity": "surface current magnitude",
        "content": {
            "kind": "image_only",
            "evidence_ids": ["unknown"],
        },
    }

    with pytest.raises(ValidationError, match="unknown evidence"):
        AntennaResults.model_validate(data)


@pytest.mark.parametrize("reason", ["not_reported", "illegible", "ambiguous"])
def test_unavailable_representation_accepts_approved_reasons(reason) -> None:
    representation = UnavailableRepresentation(
        kind="unavailable",
        reason=reason,
        description="The identified result cannot be represented.",
    )

    assert representation.reason == reason


def test_unavailable_representation_requires_a_description() -> None:
    with pytest.raises(ValidationError):
        UnavailableRepresentation(
            kind="unavailable",
            reason="illegible",
            description=" ",
        )


def test_interval_requires_two_real_source_value_endpoints() -> None:
    with pytest.raises(ValidationError):
        IntervalRepresentation.model_validate(
            {
                "kind": "interval",
                "lower": {
                    "value": None,
                    "unit": "MHz",
                    "qualifier": None,
                    "legibility": "clear",
                },
                "upper": _source_value("2.50", "GHz"),
            }
        )


def test_interval_accepts_two_explicit_endpoints() -> None:
    interval = IntervalRepresentation.model_validate(
        {
            "kind": "interval",
            "lower": _source_value("2.40", "GHz"),
            "upper": _source_value("2.50", "GHz"),
        }
    )

    assert interval.lower.value == "2.40"
    assert interval.upper.value == "2.50"
