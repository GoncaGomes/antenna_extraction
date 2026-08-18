from __future__ import annotations

import json
from copy import deepcopy

import pytest
from pydantic import ValidationError

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
    distinct_evidence = _evidence(
        source_kind="figure",
        excerpt_or_description="Distinct figure evidence.",
        source_label="Figure 2",
        legibility_note=None,
    )
    visual_evidence = _evidence(
        page_number=2,
        source_kind="graph",
        excerpt_or_description="Radiation pattern shown without numeric samples.",
        source_label="Figure 3",
        legibility_note=None,
    )
    return {
        "schema_name": "paper_extraction",
        "schema_version": "1.0.0",
        "document": {
            "document_id": "document_1",
            "page_count": 2,
            "source_filename": "paper.pdf",
            "title": "Paper",
            "doi": None,
            "sha256": "a" * 64,
        },
        "pages": [
            {"page_number": 1, "visible_label": "1"},
            {"page_number": 2, "visible_label": "2"},
        ],
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
        "material_observations": [
            {
                "observation_id": "material_1",
                "design_id": "design_2",
                "description": "A material is reported.",
                "evidence": [distinct_evidence],
                "legibility": "clear",
                "uncertainty_note": None,
                "material_name": "Material A",
                "reported_properties": [],
            }
        ],
        "parameter_observations": [],
        "geometry_observations": [],
        "feed_port_excitation_observations": [],
        "setups": [],
        "results": [
            {
                "result_id": "result_1",
                "design_id": "design_2",
                "setup_id": None,
                "origin": "unspecified",
                "metric": "radiation pattern",
                "conditions": [],
                "representation": {
                    "kind": "image_only",
                    "axes": [],
                    "trace_labels": [],
                    "annotated_points": [],
                    "evidence": [visual_evidence],
                },
                "evidence": [deepcopy(shared_evidence)],
                "uncertainty_note": None,
            }
        ],
        "derivations": [],
        "conflicts": [],
        "missing_information": [],
        "architecture_page_refs": [1, 2],
    }


def test_model_facing_schema_has_only_inline_evidence() -> None:
    schema = NuExtractPaperExtraction.model_json_schema(mode="validation")
    serialized = json.dumps(schema, sort_keys=True)
    design_properties = schema["$defs"]["NuExtractDesignRecord"]["properties"]

    assert "evidence_catalog" not in serialized
    assert "evidence_ids" not in serialized
    assert "evidence" in serialized
    for relationship in ("parent_design_id", "predecessor_design_id"):
        description = design_properties[relationship]["description"]
        assert "another record in the same designs array" in description
        assert "otherwise it must be null" in description


def test_normalization_deduplicates_exact_evidence_deterministically() -> None:
    response = NuExtractPaperExtraction.model_validate(_model_response())

    first = normalize_nuextract_extraction(response)
    second = normalize_nuextract_extraction(response)

    assert isinstance(first, PaperExtraction)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert [item.evidence_id for item in first.evidence_catalog] == [
        "evidence_1",
        "evidence_2",
        "evidence_3",
    ]
    assert first.designs[0].evidence_ids == ["evidence_1"]
    assert first.designs[1].evidence_ids == ["evidence_1"]
    assert first.material_observations[0].evidence_ids == ["evidence_2"]
    assert first.results[0].evidence_ids == ["evidence_1"]
    assert first.results[0].representation.evidence_ids == ["evidence_3"]

    declared_ids = {item.evidence_id for item in first.evidence_catalog}
    serialized = first.model_dump(mode="json")
    assert _collect_evidence_ids(serialized) <= declared_ids


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
    data["material_observations"][0]["evidence"][0] = deepcopy(
        data["designs"][0]["evidence"][0]
    )
    data["material_observations"][0]["evidence"][0][field_name] = different_value

    normalized = normalize_nuextract_extraction(
        NuExtractPaperExtraction.model_validate(data)
    )

    assert normalized.designs[0].evidence_ids == ["evidence_1"]
    assert normalized.material_observations[0].evidence_ids == ["evidence_2"]


def test_normalization_preserves_source_evidence_exactly() -> None:
    data = _model_response()
    source = InlineEvidence.model_validate(data["designs"][0]["evidence"][0])

    normalized = normalize_nuextract_extraction(
        NuExtractPaperExtraction.model_validate(data)
    )
    persisted = normalized.evidence_catalog[0].model_dump(mode="json")

    assert persisted == {
        "evidence_id": "evidence_1",
        **source.model_dump(mode="json"),
    }


@pytest.mark.parametrize("relationship", ["parent_design_id", "predecessor_design_id"])
def test_invalid_design_relationship_still_fails(relationship: str) -> None:
    data = _model_response()
    data["designs"][1][relationship] = "unknown_design"
    response = NuExtractPaperExtraction.model_validate(data)

    with pytest.raises(ValidationError, match=f"unknown {relationship.split('_')[0]}"):
        normalize_nuextract_extraction(response)


def _collect_evidence_ids(value: object) -> set[str]:
    if isinstance(value, dict):
        collected = set(value.get("evidence_ids", []))
        for nested in value.values():
            collected.update(_collect_evidence_ids(nested))
        return collected
    if isinstance(value, list):
        collected: set[str] = set()
        for nested in value:
            collected.update(_collect_evidence_ids(nested))
        return collected
    return set()
