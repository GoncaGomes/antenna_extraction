from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from numind.nuextract_utils import convert_json_schema_to_nuextract_template
from pydantic import ValidationError

from antenna_ingest.contracts.common import DocumentReference, PageRecord
from antenna_ingest.contracts.paper_extraction import PaperExtraction
from antenna_ingest.contracts.schema_generation import render_json_schema
from antenna_ingest.extraction.nuextract_contract import (
    InlineEvidence,
    NuExtractObservationRecord,
    NuExtractPaperExtraction,
    NuExtractResultRepresentation,
    NuExtractSetupRecord,
    build_nuextract_template,
    normalize_nuextract_extraction,
)


def _evidence(
    *,
    page_number: int = 1,
    source_kind: str = "text",
    excerpt_or_description: str = "  Exact source\u00a0text\nwith spacing.  ",
    source_label: str | None = "Source A",
    bounding_region: dict | None = None,
    legibility_note: str | None = "Partially obscured",
) -> dict:
    return {
        "page_number": page_number,
        "source_kind": source_kind,
        "excerpt_or_description": excerpt_or_description,
        "source_label": source_label,
        "bounding_region": bounding_region
        or {"x0": 0.1, "y0": 0.2, "x1": 0.8, "y1": 0.9},
        "legibility_note": legibility_note,
    }


def _model_response() -> dict:
    shared_evidence = _evidence()
    distinct_evidence = _evidence(source_label="Distinct source label")
    page_two_evidence = _evidence(
        page_number=2,
        source_kind="figure",
        excerpt_or_description="Figure 2 shows the final geometry.",
        source_label="Figure 2",
        legibility_note=None,
    )
    result_evidence = _evidence(
        page_number=3,
        source_kind="table",
        excerpt_or_description="Table I reports 2.45 GHz.",
        source_label="Table I",
        legibility_note=None,
    )
    graph_evidence = _evidence(
        page_number=3,
        source_kind="graph",
        excerpt_or_description="Figure 3 shows the measured response.",
        source_label="Figure 3",
        legibility_note=None,
    )
    map_evidence = _evidence(
        page_number=3,
        source_kind="figure",
        excerpt_or_description="Figure 4 shows current distribution.",
        source_label="Figure 4",
        legibility_note=None,
    )
    return {
        "document": {
            "title": "Compact extraction paper",
            "doi": "10.1000/example",
        },
        "designs": [
            {
                "design_id": "design_1",
                "name": "First design",
                "role": "candidate",
                "description": None,
                "parent_design_id": None,
                "predecessor_design_id": None,
                "evidence": [shared_evidence],
            },
            {
                "design_id": "design_2",
                "name": "Second design",
                "role": "final",
                "description": None,
                "parent_design_id": "design_1",
                "predecessor_design_id": None,
                "evidence": [deepcopy(shared_evidence)],
            },
        ],
        "observations": [
            {
                "kind": "material",
                "observation_id": "material_1",
                "design_id": "design_2",
                "description": "A material is reported.",
                "evidence": [distinct_evidence],
                "legibility": "clear",
                "uncertainty_note": None,
                "material_name": "Material A",
                "reported_properties": [],
            },
            {
                "kind": "parameter",
                "observation_id": "parameter_1",
                "design_id": "design_2",
                "description": "A parameter is reported.",
                "evidence": [deepcopy(shared_evidence)],
                "legibility": "clear",
                "uncertainty_note": None,
                "symbol": "f_0",
                "reported_value": {
                    "value": "2.45",
                    "unit": "GHz",
                    "qualifier": None,
                    "legibility": "clear",
                },
            },
            {
                "kind": "geometry",
                "observation_id": "geometry_1",
                "design_id": "design_2",
                "description": "A slot is shown.",
                "evidence": [page_two_evidence],
                "legibility": "clear",
                "uncertainty_note": None,
                "source_feature_label": "slot",
            },
            {
                "kind": "feed",
                "observation_id": "feed_1",
                "design_id": "design_2",
                "description": "A feed is reported.",
                "evidence": [deepcopy(page_two_evidence)],
                "legibility": "clear",
                "uncertainty_note": None,
                "reported_impedance": None,
            },
            {
                "kind": "port",
                "observation_id": "port_1",
                "design_id": "design_2",
                "description": "A port is reported.",
                "evidence": [deepcopy(page_two_evidence)],
                "legibility": "clear",
                "uncertainty_note": None,
                "reported_impedance": None,
            },
            {
                "kind": "excitation",
                "observation_id": "excitation_1",
                "design_id": "design_2",
                "description": "An excitation is reported.",
                "evidence": [deepcopy(page_two_evidence)],
                "legibility": "clear",
                "uncertainty_note": None,
                "reported_impedance": None,
            },
        ],
        "setups": [
            {
                "kind": "simulation",
                "setup_id": "setup_1",
                "description": "Simulation setup.",
                "evidence": [deepcopy(result_evidence)],
                "legibility": "clear",
                "uncertainty_note": None,
                "software": None,
                "solver_or_method": None,
                "model": None,
                "conditions": [],
            }
        ],
        "results": [
            {
                "result_id": "result_scalar",
                "design_id": "design_2",
                "setup_id": "setup_1",
                "origin": "simulated",
                "metric": "resonant frequency",
                "conditions": [],
                "representation": {
                    "kind": "scalar",
                    "scalar_value": {
                        "value": "2.45",
                        "unit": "GHz",
                        "qualifier": None,
                        "legibility": "clear",
                    },
                },
                "evidence": [result_evidence],
                "uncertainty_note": None,
            },
            {
                "result_id": "result_graph",
                "design_id": "design_2",
                "setup_id": None,
                "origin": "measured",
                "metric": "return loss",
                "conditions": [],
                "representation": {
                    "kind": "image_only",
                    "image_axes": [],
                    "image_trace_labels": [],
                    "image_annotated_points": [],
                },
                "evidence": [graph_evidence],
                "uncertainty_note": None,
            },
            {
                "result_id": "result_map",
                "design_id": "design_2",
                "setup_id": None,
                "origin": "unspecified",
                "metric": "surface current",
                "conditions": [],
                "representation": {
                    "kind": "spatial_map",
                    "spatial_quantity": "surface current",
                    "spatial_content_kind": "image_only",
                    "spatial_map_type_or_component": "magnitude",
                    "spatial_plane_or_cut": None,
                    "spatial_legend_or_scale_label": None,
                    "spatial_annotated_points": [],
                },
                "evidence": [map_evidence],
                "uncertainty_note": None,
            },
        ],
        "derivations": [
            {
                "derivation_id": "derivation_1",
                "description": "A source equation is reported.",
                "expression_text": "L = c / (2 f)",
                "symbols": ["L", "c", "f"],
                "evidence": [deepcopy(page_two_evidence)],
            }
        ],
        "conflicts": [
            {
                "conflict_id": "conflict_1",
                "description": "Two results conflict.",
                "related_refs": [
                    {"kind": "result", "id": "result_scalar"},
                    {"kind": "result", "id": "result_graph"},
                ],
                "evidence": [deepcopy(result_evidence), deepcopy(graph_evidence)],
            }
        ],
        "missing_information": [
            {
                "missing_information_id": "missing_1",
                "description": "Conductor thickness is not reported.",
                "related_refs": [{"kind": "design", "id": "design_2"}],
                "evidence": [],
            }
        ],
    }


def _normalize(data: dict) -> PaperExtraction:
    return normalize_nuextract_extraction(
        NuExtractPaperExtraction.model_validate(data),
        document=DocumentReference(
            document_id="document_1",
            page_count=3,
            source_filename="paper.pdf",
            title=data["document"]["title"],
            doi=data["document"]["doi"],
            sha256="a" * 64,
        ),
        pages=[PageRecord(page_number=number) for number in (1, 2, 3)],
    )


def _source_value(value: str = "1.0", unit: str = "GHz") -> dict:
    return {
        "value": value,
        "unit": unit,
        "qualifier": None,
        "legibility": "clear",
    }


def _reported_point() -> dict:
    return {
        "values": [{"name": "frequency", "value": _source_value()}],
        "label": "reported point",
    }


def _representation_cases() -> list[tuple[dict, dict]]:
    scalar = _source_value()
    lower = _source_value("1.0")
    upper = _source_value("2.0")
    x_value = _source_value("1.0")
    y_value = _source_value("-10", "dB")
    angle = _source_value("0", "degree")
    angular_value = _source_value("3", "dBi")
    return [
        (
            {"kind": "scalar", "scalar_value": scalar},
            {"kind": "scalar", "value": scalar},
        ),
        (
            {
                "kind": "interval",
                "interval_lower": lower,
                "interval_upper": upper,
            },
            {"kind": "interval", "lower": lower, "upper": upper},
        ),
        (
            {"kind": "point_collection", "collection_points": [_reported_point()]},
            {"kind": "point_collection", "points": [_reported_point()]},
        ),
        (
            {
                "kind": "sampled_series",
                "series_x_axis": {"name": "frequency", "unit": "GHz"},
                "series_y_axis": {"name": "S11", "unit": "dB"},
                "series_trace_label": "measured",
                "series_points": [{"x": x_value, "y": y_value}],
            },
            {
                "kind": "sampled_series",
                "x_axis": {"name": "frequency", "unit": "GHz"},
                "y_axis": {"name": "S11", "unit": "dB"},
                "trace_label": "measured",
                "points": [{"x": x_value, "y": y_value}],
            },
        ),
        (
            {
                "kind": "matrix",
                "matrix_rows": [[scalar]],
                "matrix_row_labels": ["row"],
                "matrix_column_labels": ["column"],
            },
            {
                "kind": "matrix",
                "rows": [[scalar]],
                "row_labels": ["row"],
                "column_labels": ["column"],
            },
        ),
        (
            {
                "kind": "angular_pattern",
                "angular_coordinate": "theta",
                "angular_unit": "degree",
                "angular_plane_or_cut": "phi=0",
                "angular_fixed_angle": None,
                "angular_component_or_polarization": "co-polar",
                "angular_radial_quantity": "gain",
                "angular_points": [{"angle": angle, "value": angular_value}],
            },
            {
                "kind": "angular_pattern",
                "angular_coordinate": "theta",
                "angular_unit": "degree",
                "plane_or_cut": "phi=0",
                "fixed_angle": None,
                "component_or_polarization": "co-polar",
                "radial_quantity": "gain",
                "points": [{"angle": angle, "value": angular_value}],
            },
        ),
        (
            {
                "kind": "spatial_map",
                "spatial_quantity": "SAR",
                "spatial_content_kind": "sampled",
                "spatial_coordinate_description": "Cartesian coordinates",
                "spatial_samples": [_reported_point()],
            },
            {
                "kind": "spatial_map",
                "quantity": "SAR",
                "content": {
                    "kind": "sampled",
                    "coordinate_description": "Cartesian coordinates",
                    "samples": [_reported_point()],
                },
            },
        ),
        (
            {
                "kind": "spatial_map",
                "spatial_quantity": "surface current",
                "spatial_content_kind": "image_only",
                "spatial_map_type_or_component": "magnitude",
                "spatial_plane_or_cut": "antenna surface",
                "spatial_legend_or_scale_label": "A/m",
                "spatial_annotated_points": [],
            },
            {
                "kind": "spatial_map",
                "quantity": "surface current",
                "content": {
                    "kind": "image_only",
                    "map_type_or_component": "magnitude",
                    "plane_or_cut": "antenna surface",
                    "legend_or_scale_label": "A/m",
                    "annotated_points": [],
                },
            },
        ),
        (
            {
                "kind": "image_only",
                "image_axes": [{"name": "frequency", "unit": "GHz"}],
                "image_trace_labels": ["measured"],
                "image_annotated_points": [_reported_point()],
            },
            {
                "kind": "image_only",
                "axes": [{"name": "frequency", "unit": "GHz"}],
                "trace_labels": ["measured"],
                "annotated_points": [_reported_point()],
            },
        ),
        (
            {"kind": "qualitative", "qualitative_observation": "Broadside pattern"},
            {"kind": "qualitative", "observation": "Broadside pattern"},
        ),
        (
            {
                "kind": "unavailable",
                "unavailable_reason": "illegible",
                "unavailable_description": "The plotted value is illegible.",
            },
            {
                "kind": "unavailable",
                "reason": "illegible",
                "description": "The plotted value is illegible.",
            },
        ),
    ]


def _normalize_single_representation(representation: dict):
    data = _model_response()
    data["setups"] = []
    data["conflicts"] = []
    data["results"] = [
        {
            "result_id": "result_test",
            "design_id": "design_2",
            "setup_id": None,
            "origin": "unspecified",
            "metric": "test metric",
            "conditions": [],
            "representation": representation,
            "evidence": [_evidence(page_number=3)],
            "uncertainty_note": None,
        }
    ]
    return _normalize(data).results[0]


def test_model_facing_schema_is_compact_and_flat() -> None:
    schema = NuExtractPaperExtraction.model_json_schema(mode="validation")
    properties = schema["properties"]
    document_properties = schema["$defs"]["NuExtractDocumentMetadata"]["properties"]

    assert set(properties) == {
        "document",
        "designs",
        "observations",
        "setups",
        "results",
        "derivations",
        "conflicts",
        "missing_information",
    }
    assert set(document_properties) == {"title", "doi"}
    for removed in (
        "schema_name",
        "schema_version",
        "pages",
        "architecture_page_refs",
        "material_observations",
        "parameter_observations",
        "geometry_observations",
        "feed_port_excitation_observations",
    ):
        assert removed not in properties
    serialized = json.dumps(schema, sort_keys=True)
    assert "evidence_catalog" not in serialized
    assert "evidence_ids" not in serialized


def test_native_template_conversion_is_complete_compact_and_deterministic() -> None:
    schema = NuExtractPaperExtraction.model_json_schema(mode="validation")
    template, dropped_branches, _descriptions = (
        convert_json_schema_to_nuextract_template(schema)
    )
    built_template = build_nuextract_template()
    schema_json = json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
    template_json = json.dumps(
        built_template,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    assert dropped_branches == []
    assert isinstance(template, dict)
    assert template == built_template == build_nuextract_template()
    assert list(template) == [
        "document",
        "designs",
        "observations",
        "setups",
        "results",
        "derivations",
        "conflicts",
        "missing_information",
    ]
    assert template["observations"][0]["kind"] == [
        "material",
        "parameter",
        "geometry",
        "feed",
        "port",
        "excitation",
    ]
    assert template["setups"][0]["kind"] == [
        "simulation",
        "measurement",
        "analytical",
    ]
    representation = template["results"][0]["representation"]
    assert representation["kind"] == [
        "scalar",
        "interval",
        "point_collection",
        "sampled_series",
        "matrix",
        "angular_pattern",
        "spatial_map",
        "image_only",
        "qualitative",
        "unavailable",
    ]
    assert representation["spatial_content_kind"] == ["sampled", "image_only"]
    assert {"collection_points", "series_points", "angular_points"} <= set(
        representation
    )
    for keyword in ("$defs", "$ref", "anyOf", "oneOf", "allOf"):
        assert keyword not in template_json
    assert len(template_json) < len(schema_json) * 0.75


def test_final_paper_extraction_schema_remains_unchanged() -> None:
    schema_path = (
        Path(__file__).parents[2]
        / "schemas"
        / "generated"
        / "paper_extraction.schema.json"
    )

    assert render_json_schema(PaperExtraction) == schema_path.read_bytes()


@pytest.mark.parametrize(
    ("kind", "active_fields"),
    [
        ("material", {"material_name": "Rogers 4003C"}),
        ("parameter", {"symbol": "f_0", "reported_value": _source_value()}),
        ("geometry", {"source_feature_label": "slot"}),
        ("feed", {"reported_impedance": _source_value("50", "ohm")}),
        ("port", {"reported_impedance": _source_value("50", "ohm")}),
        ("excitation", {"reported_impedance": _source_value("50", "ohm")}),
    ],
)
def test_flat_observation_accepts_each_kind(kind: str, active_fields: dict) -> None:
    observation = NuExtractObservationRecord.model_validate(
        {
            "observation_id": f"{kind}_1",
            "design_id": "design_1",
            "description": "Source-supported observation.",
            "evidence": [_evidence()],
            "kind": kind,
            **active_fields,
        }
    )

    assert observation.kind == kind


def test_flat_observation_rejects_populated_inactive_fields() -> None:
    with pytest.raises(ValidationError, match="inactive fields.*material_name"):
        NuExtractObservationRecord.model_validate(
            {
                "observation_id": "parameter_1",
                "description": "Parameter observation.",
                "evidence": [_evidence()],
                "kind": "parameter",
                "material_name": "Inactive material",
            }
        )


@pytest.mark.parametrize(
    ("kind", "active_fields"),
    [
        ("simulation", {"software": "CST", "conditions": []}),
        ("measurement", {"equipment": ["VNA"], "environment": "laboratory"}),
        ("analytical", {"method": "closed form", "assumptions": ["lossless"]}),
    ],
)
def test_flat_setup_accepts_and_normalizes_each_kind(
    kind: str,
    active_fields: dict,
) -> None:
    setup_data = {
        "setup_id": f"setup_{kind}",
        "description": f"{kind} setup",
        "evidence": [_evidence(page_number=3)],
        "kind": kind,
        **active_fields,
    }
    assert NuExtractSetupRecord.model_validate(setup_data).kind == kind

    data = _model_response()
    data["setups"] = [setup_data]
    data["results"] = []
    data["conflicts"] = []
    normalized = _normalize(data)

    assert normalized.setups[0].kind == kind
    assert normalized.setups[0].setup_id == f"setup_{kind}"


def test_flat_setup_rejects_populated_inactive_fields() -> None:
    with pytest.raises(ValidationError, match="inactive fields.*equipment"):
        NuExtractSetupRecord.model_validate(
            {
                "setup_id": "setup_1",
                "description": "Simulation setup.",
                "evidence": [_evidence()],
                "kind": "simulation",
                "equipment": ["VNA"],
            }
        )


@pytest.mark.parametrize(
    "representation",
    [
        {"kind": "scalar", "scalar_value": None},
        {
            "kind": "interval",
            "interval_lower": _source_value(),
            "interval_upper": None,
        },
        {"kind": "point_collection", "collection_points": []},
        {
            "kind": "sampled_series",
            "series_x_axis": {"name": "frequency"},
            "series_y_axis": {"name": "S11"},
            "series_points": [],
        },
        {"kind": "matrix", "matrix_rows": [[]]},
        {
            "kind": "angular_pattern",
            "angular_coordinate": "theta",
            "angular_radial_quantity": "gain",
            "angular_points": [],
        },
        {
            "kind": "spatial_map",
            "spatial_quantity": None,
            "spatial_content_kind": "image_only",
        },
        {"kind": "qualitative", "qualitative_observation": None},
        {
            "kind": "unavailable",
            "unavailable_reason": None,
            "unavailable_description": "Missing value.",
        },
    ],
)
def test_flat_result_representation_enforces_required_fields(
    representation: dict,
) -> None:
    with pytest.raises(ValidationError, match="required fields|matrix rows"):
        NuExtractResultRepresentation.model_validate(representation)


def test_flat_result_representation_rejects_populated_inactive_fields() -> None:
    with pytest.raises(
        ValidationError,
        match="inactive fields.*qualitative_observation",
    ):
        NuExtractResultRepresentation.model_validate(
            {
                "kind": "scalar",
                "scalar_value": _source_value(),
                "qualitative_observation": "Inactive finding",
            }
        )


def test_flat_spatial_map_rejects_fields_from_inactive_content_kind() -> None:
    with pytest.raises(ValidationError, match="inactive spatial-map fields"):
        NuExtractResultRepresentation.model_validate(
            {
                "kind": "spatial_map",
                "spatial_quantity": "current",
                "spatial_content_kind": "image_only",
                "spatial_samples": [_reported_point()],
            }
        )


@pytest.mark.parametrize(("flat", "expected"), _representation_cases())
def test_every_flat_representation_normalizes_to_final_contract(
    flat: dict,
    expected: dict,
) -> None:
    result = _normalize_single_representation(deepcopy(flat))
    actual = result.representation.model_dump(mode="json")

    if expected["kind"] == "image_only":
        expected["evidence_ids"] = list(result.evidence_ids)
    if (
        expected["kind"] == "spatial_map"
        and expected["content"]["kind"] == "image_only"
    ):
        expected["content"]["evidence_ids"] = list(result.evidence_ids)
    assert actual == expected


def test_normalization_routes_observations_and_preserves_ids_and_references() -> None:
    normalized = _normalize(_model_response())

    assert [item.observation_id for item in normalized.material_observations] == [
        "material_1"
    ]
    assert [item.observation_id for item in normalized.parameter_observations] == [
        "parameter_1"
    ]
    assert [item.observation_id for item in normalized.geometry_observations] == [
        "geometry_1"
    ]
    assert [
        (item.observation_id, item.observation_kind)
        for item in normalized.feed_port_excitation_observations
    ] == [
        ("feed_1", "feed"),
        ("port_1", "port"),
        ("excitation_1", "excitation"),
    ]
    assert normalized.designs[1].design_id == "design_2"
    assert normalized.designs[1].parent_design_id == "design_1"
    assert normalized.results[0].setup_id == "setup_1"
    assert normalized.conflicts[0].related_refs[0].id == "result_scalar"


def test_normalization_deduplicates_evidence_and_preserves_content() -> None:
    data = _model_response()
    source = InlineEvidence.model_validate(data["designs"][0]["evidence"][0])

    first = _normalize(data)
    second = _normalize(data)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.designs[0].evidence_ids == first.designs[1].evidence_ids
    assert first.parameter_observations[0].evidence_ids == first.designs[0].evidence_ids
    assert first.material_observations[0].evidence_ids != first.designs[0].evidence_ids
    evidence_id = first.designs[0].evidence_ids[0]
    persisted = next(
        item for item in first.evidence_catalog if item.evidence_id == evidence_id
    )
    assert persisted.model_dump(mode="json") == {
        "evidence_id": evidence_id,
        **source.model_dump(mode="json"),
    }


@pytest.mark.parametrize(
    ("field_name", "different_value"),
    [
        ("page_number", 2),
        ("source_kind", "caption"),
        ("excerpt_or_description", "Different source text."),
        ("source_label", "Different label"),
        ("bounding_region", {"x0": 0.2, "y0": 0.2, "x1": 0.8, "y1": 0.9}),
        ("legibility_note", "Different legibility note"),
    ],
)
def test_every_evidence_field_participates_in_exact_deduplication(
    field_name: str,
    different_value: object,
) -> None:
    data = _model_response()
    data["observations"][0]["evidence"][0] = deepcopy(data["designs"][0]["evidence"][0])
    data["observations"][0]["evidence"][0][field_name] = different_value

    normalized = _normalize(data)

    assert normalized.designs[0].evidence_ids != (
        normalized.material_observations[0].evidence_ids
    )


def test_visual_representations_reuse_parent_result_evidence() -> None:
    normalized = _normalize(_model_response())
    graph = normalized.results[1]
    spatial_map = normalized.results[2]

    assert graph.representation.evidence_ids == graph.evidence_ids
    assert graph.representation.evidence_ids is not graph.evidence_ids
    assert spatial_map.representation.content.evidence_ids == spatial_map.evidence_ids
    assert (
        spatial_map.representation.content.evidence_ids is not spatial_map.evidence_ids
    )


def test_missing_information_and_architecture_pages_are_derived() -> None:
    normalized = _normalize(_model_response())

    assert normalized.missing_information[0].evidence_ids == []
    assert normalized.architecture_page_refs == [1, 2]


def test_architecture_evidence_on_an_undeclared_page_still_fails() -> None:
    data = _model_response()
    data["observations"][0]["evidence"][0]["page_number"] = 4

    with pytest.raises(ValidationError, match="references undeclared page 4"):
        _normalize(data)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda data: data["results"][0].update(design_id="unknown"), "unknown design"),
        (lambda data: data["results"][0].update(setup_id="unknown"), "unknown setup"),
        (
            lambda data: data["conflicts"][0]["related_refs"][0].update(id="unknown"),
            "unknown result reference",
        ),
    ],
)
def test_unknown_cross_references_still_fail(mutation, message: str) -> None:
    data = _model_response()
    mutation(data)

    with pytest.raises(ValidationError, match=message):
        _normalize(data)


@pytest.mark.parametrize("relationship", ["parent_design_id", "predecessor_design_id"])
def test_invalid_design_relationship_still_fails(relationship: str) -> None:
    data = _model_response()
    data["designs"][1][relationship] = "unknown_design"

    with pytest.raises(ValidationError, match=f"unknown {relationship.split('_')[0]}"):
        _normalize(data)


def test_duplicate_record_ids_still_fail() -> None:
    data = _model_response()
    duplicate = deepcopy(data["designs"][0])
    duplicate["name"] = "Duplicate design ID"
    data["designs"].append(duplicate)

    with pytest.raises(ValidationError, match="duplicate IDs in design registry"):
        _normalize(data)
