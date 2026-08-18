from __future__ import annotations

import json
from copy import deepcopy

import pytest
from pydantic import ValidationError

from antenna_ingest.contracts.common import DocumentReference, PageRecord
from antenna_ingest.contracts.paper_extraction import PaperExtraction
from antenna_ingest.extraction.nuextract_contract import (
    InlineEvidence,
    NuExtractPaperExtraction,
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
                    "value": {
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
                    "axes": [],
                    "trace_labels": [],
                    "annotated_points": [],
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
                    "quantity": "surface current",
                    "content": {
                        "kind": "image_only",
                        "map_type_or_component": "magnitude",
                        "plane_or_cut": None,
                        "legend_or_scale_label": None,
                        "annotated_points": [],
                    },
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


def test_model_facing_schema_is_compact_and_uses_discriminated_observations() -> None:
    schema = NuExtractPaperExtraction.model_json_schema(mode="validation")
    properties = schema["properties"]
    document_properties = schema["$defs"]["NuExtractDocumentMetadata"]["properties"]
    serialized = json.dumps(schema, sort_keys=True)

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
    assert '"discriminator": {"mapping"' in serialized
    assert "evidence_catalog" not in serialized
    assert "evidence_ids" not in serialized


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
