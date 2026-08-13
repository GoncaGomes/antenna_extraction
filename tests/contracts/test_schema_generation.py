from __future__ import annotations

import json
from pathlib import Path

from antenna_ingest.contracts.antenna_architecture import AntennaArchitecture
from antenna_ingest.contracts.antenna_results import AntennaResults
from antenna_ingest.contracts.paper_extraction import PaperExtraction
from antenna_ingest.contracts.schema_generation import (
    DEFAULT_SCHEMA_DIRECTORY,
    generate_json_schemas,
    render_json_schema,
)


def test_schema_rendering_is_deterministic() -> None:
    for model in (PaperExtraction, AntennaResults, AntennaArchitecture):
        assert render_json_schema(model) == render_json_schema(model)


def test_generated_schemas_match_checked_in_files(tmp_path: Path) -> None:
    generated = generate_json_schemas(tmp_path)

    assert {path.name for path in generated} == {
        "paper_extraction.schema.json",
        "antenna_results.schema.json",
        "antenna_architecture.schema.json",
    }
    for generated_path in generated:
        checked_in = DEFAULT_SCHEMA_DIRECTORY / generated_path.name
        assert generated_path.read_bytes() == checked_in.read_bytes()


def test_schemas_expose_strict_discriminated_contracts() -> None:
    for model in (PaperExtraction, AntennaResults, AntennaArchitecture):
        schema = json.loads(render_json_schema(model))
        serialized = json.dumps(schema, sort_keys=True).lower()

        assert schema["additionalProperties"] is False
        assert '"discriminator"' in serialized
        assert '"normalized"' not in serialized
        assert '"normalised"' not in serialized
        assert '"solver_commands"' not in serialized
        assert '"boolean_operations"' not in serialized
        assert '"safe_expression"' not in serialized
        assert '"patchantenna"' not in serialized
        assert '"cst"' not in serialized


def test_nested_object_schemas_forbid_unknown_fields() -> None:
    schema = json.loads(render_json_schema(PaperExtraction))
    object_definitions = [
        definition
        for definition in schema["$defs"].values()
        if definition.get("type") == "object"
    ]

    assert object_definitions
    assert all(
        definition.get("additionalProperties") is False
        for definition in object_definitions
    )


def test_setup_discriminator_has_exact_approved_kinds() -> None:
    schema = json.loads(render_json_schema(PaperExtraction))

    setup_kinds = {
        schema["$defs"][definition]["properties"]["kind"]["const"]
        for definition in (
            "SimulationSetup",
            "MeasurementSetup",
            "AnalyticalSetup",
        )
    }

    assert setup_kinds == {"simulation", "measurement", "analytical"}


def test_field_map_content_schema_has_explicit_discriminated_variants() -> None:
    schema = json.loads(render_json_schema(PaperExtraction))
    content_schema = schema["$defs"]["FieldMapRepresentation"]["properties"][
        "content"
    ]

    assert content_schema["discriminator"]["propertyName"] == "kind"
    assert set(content_schema["discriminator"]["mapping"]) == {
        "image_only",
        "sampled",
    }


def test_architecture_schema_has_exact_geometry_and_relationship_kinds() -> None:
    schema = json.loads(render_json_schema(AntennaArchitecture))

    geometry_kinds = {
        schema["$defs"][definition]["properties"]["kind"]["const"]
        for definition in (
            "RectangleGeometry",
            "CircleGeometry",
            "EllipseGeometry",
            "AnnulusGeometry",
            "PolygonGeometry",
            "SegmentedProfileGeometry",
            "BoxGeometry",
            "CylinderGeometry",
            "ConeGeometry",
            "SphereGeometry",
            "ExtrusionGeometry",
            "RevolutionGeometry",
            "WirePathGeometry",
            "SweepGeometry",
            "SurfaceGeometry",
            "MeshGeometry",
            "InstanceGeometry",
            "UnresolvedGeometry",
            "RelationshipResultGeometry",
        )
    }
    relationship_kinds = {
        schema["$defs"][definition]["properties"]["kind"]["const"]
        for definition in (
            "SubtractRelationship",
            "UniteRelationship",
            "IntersectRelationship",
            "ContactRelationship",
            "ContainedInRelationship",
            "AlignedWithRelationship",
            "PatternInstanceRelationship",
        )
    }

    assert geometry_kinds == {
        "rectangle",
        "circle",
        "ellipse",
        "annulus",
        "polygon",
        "segmented_profile",
        "box",
        "cylinder",
        "cone",
        "sphere",
        "extrusion",
        "revolution",
        "wire_path",
        "sweep",
        "surface",
        "mesh",
        "instance",
        "unresolved",
        "relationship_result",
    }
    assert relationship_kinds == {
        "subtract",
        "unite",
        "intersect",
        "contact",
        "contained_in",
        "aligned_with",
        "pattern_instance",
    }


def test_architecture_schema_excludes_deferred_and_family_specific_contracts() -> None:
    schema = json.loads(render_json_schema(AntennaArchitecture))
    serialized = json.dumps(schema, sort_keys=True).lower()

    for forbidden in (
        "normalized",
        "normalised",
        "patchantenna",
        "pifa",
        "hornantenna",
        "helixantenna",
        "cst",
        "solver_commands",
        "model_client",
        "endpoint",
    ):
        assert forbidden not in serialized
