from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from antenna_ingest.contracts.antenna_results import AntennaResults


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
        "complete",
    ),
    (
        "interval",
        {
            "kind": "interval",
            "lower": _source_value("2.40", "GHz"),
            "upper": _source_value("2.50", "GHz"),
        },
        "complete",
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
        "complete",
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
        "partial_numeric",
    ),
    (
        "matrix",
        {
            "kind": "matrix",
            "rows": [[_source_value("1"), _source_value("0")]],
            "row_labels": ["row 1"],
            "column_labels": ["col 1", "col 2"],
        },
        "complete",
    ),
    (
        "angular_pattern",
        {
            "kind": "angular_pattern",
            "angular_coordinate": "theta",
            "angular_unit": "degree",
            "plane_or_cut": "phi = 0°",
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
        "partial_numeric",
    ),
    (
        "field_map",
        {
            "kind": "field_map",
            "field_or_current": "current",
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
        "complete",
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
        "complete",
    ),
    (
        "qualitative",
        {
            "kind": "qualitative",
            "observation": "The measured response remains stable.",
        },
        "complete",
    ),
]


@pytest.mark.parametrize(("kind", "representation", "completeness"), REPRESENTATIONS)
def test_all_result_representations_validate(
    antenna_results_data,
    kind,
    representation,
    completeness,
) -> None:
    data = deepcopy(antenna_results_data)
    result = data["results"][0]
    result["setup_id"] = None
    result["representation"] = representation
    result["extraction_completeness"] = completeness
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


def test_complete_result_rejects_a_missing_nested_source_value(
    antenna_results_data,
) -> None:
    data = deepcopy(antenna_results_data)
    result = data["results"][0]
    result["representation"] = {
        "kind": "scalar",
        "value": {
            "value": None,
            "unit": "ohm",
            "qualifier": None,
            "legibility": "missing",
        },
    }
    result["extraction_completeness"] = "complete"

    with pytest.raises(ValidationError, match="cannot contain missing or illegible"):
        AntennaResults.model_validate(data)


def test_missing_result_rejects_a_legible_nested_source_value(
    antenna_results_data,
) -> None:
    data = deepcopy(antenna_results_data)
    result = data["results"][0]
    result["representation"] = {
        "kind": "scalar",
        "value": _source_value("47.98", "ohm"),
    }
    result["legibility"] = "missing"
    result["extraction_completeness"] = "missing"

    with pytest.raises(ValidationError, match="every source value to be missing"):
        AntennaResults.model_validate(data)


def test_partial_numeric_result_rejects_a_missing_nested_source_value(
    antenna_results_data,
) -> None:
    data = deepcopy(antenna_results_data)
    result = data["results"][0]
    result["setup_id"] = None
    result["representation"] = {
        "kind": "sampled_series",
        "x_axis": {"name": "frequency", "unit": "GHz"},
        "y_axis": {"name": "S11", "unit": "dB"},
        "trace_label": "reported trace",
        "points": [
            {
                "x": {
                    "value": None,
                    "unit": "GHz",
                    "qualifier": None,
                    "legibility": "missing",
                },
                "y": _source_value("-10", "dB"),
            }
        ],
    }
    result["extraction_completeness"] = "partial_numeric"

    with pytest.raises(ValidationError, match="cannot contain missing or illegible"):
        AntennaResults.model_validate(data)


def test_sampled_field_map_without_samples_is_rejected(
    antenna_results_data,
) -> None:
    data = deepcopy(antenna_results_data)
    result = data["results"][0]
    result["representation"] = {
        "kind": "field_map",
        "field_or_current": "field",
        "quantity": "electric field magnitude",
        "content": {
            "kind": "sampled",
            "coordinate_description": "reported local x-y coordinates",
            "samples": [],
        },
    }

    with pytest.raises(ValidationError, match="at least 1 item"):
        AntennaResults.model_validate(data)


def test_image_only_field_map_with_known_evidence_is_valid(
    antenna_results_data,
) -> None:
    data = deepcopy(antenna_results_data)
    result = data["results"][0]
    result["representation"] = {
        "kind": "field_map",
        "field_or_current": "current",
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
    assert validated.results[0].representation.content.evidence_ids == [
        "ev_simulated"
    ]


def test_image_only_field_map_requires_evidence(
    antenna_results_data,
) -> None:
    data = deepcopy(antenna_results_data)
    result = data["results"][0]
    result["representation"] = {
        "kind": "field_map",
        "field_or_current": "current",
        "quantity": "surface current magnitude",
        "content": {
            "kind": "image_only",
            "evidence_ids": [],
        },
    }

    with pytest.raises(ValidationError, match="at least 1 item"):
        AntennaResults.model_validate(data)


def test_image_only_field_map_rejects_unknown_evidence(
    antenna_results_data,
) -> None:
    data = deepcopy(antenna_results_data)
    result = data["results"][0]
    result["representation"] = {
        "kind": "field_map",
        "field_or_current": "current",
        "quantity": "surface current magnitude",
        "content": {
            "kind": "image_only",
            "evidence_ids": ["unknown"],
        },
    }

    with pytest.raises(ValidationError, match="unknown evidence"):
        AntennaResults.model_validate(data)


@pytest.mark.parametrize("state", ["missing", "illegible"])
def test_missing_and_illegible_results_remain_explicit(
    antenna_results_data,
    state,
) -> None:
    data = deepcopy(antenna_results_data)
    result = data["results"][0]
    result["setup_id"] = None
    result["representation"] = {
        "kind": "scalar",
        "value": {
            "value": None,
            "unit": "dB",
            "qualifier": None,
            "legibility": state,
        },
    }
    result["legibility"] = state
    result["extraction_completeness"] = state
    data["results"] = [result]
    data["conflicts"] = []

    validated = AntennaResults.model_validate(data)

    assert validated.results[0].representation.value.value is None
    assert validated.results[0].extraction_completeness == state
